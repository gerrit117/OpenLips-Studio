#include "core.h"
#include <cstdio>
#include <cwctype>
#include <cstdlib>
#include <cstring>
#include "cJSON.h"
#include "bearssl.h"

namespace openlips {
bool hex_id(const std::string& value, size_t length)
{
    if (value.size() != length) return false;
    for (size_t i = 0; i < value.size(); ++i)
        if (!((value[i] >= '0' && value[i] <= '9') || (value[i] >= 'a' && value[i] <= 'f'))) return false;
    return true;
}
bool private_ip(const std::string& host, bool loopback)
{
    unsigned bytes[4] = {0};
    size_t part = 0, digits = 0;
    for (size_t i = 0; i < host.size(); ++i) {
        char c = host[i];
        if (c == '.') {
            if (!digits || part == 3) return false;
            ++part; digits = 0;
        } else {
            if (c < '0' || c > '9' || ++digits > 3) return false;
            bytes[part] = bytes[part] * 10 + c - '0';
            if (bytes[part] > 255) return false;
        }
    }
    return part == 3 && digits && ((loopback && bytes[0] == 127) || bytes[0] == 10 ||
        (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31) || (bytes[0] == 192 && bytes[1] == 168));
}
std::wstring wide(const std::string& value)
{
    std::wstring out;
    for (size_t i = 0; i < value.size();) {
        unsigned c = static_cast<unsigned char>(value[i++]);
        unsigned more = 0, minimum = 0;
        if (c >= 0xc2 && c <= 0xdf) { c &= 31; more = 1; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { c &= 15; more = 2; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { c &= 7; more = 3; minimum = 0x10000; }
        else if (c >= 128) { out += L'?'; continue; }
        bool valid = i + more <= value.size();
        for (unsigned n = 0; n < more && valid; ++n) {
            unsigned next = static_cast<unsigned char>(value[i]);
            if ((next & 0xc0) != 0x80) valid = false;
            else { ++i; c = (c << 6) | (next & 63); }
        }
        if (!valid || c < minimum || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) out += L'?';
        else if (c <= 0xffff) out += static_cast<wchar_t>(c < 32 ? ' ' : c);
        else { c -= 0x10000; out += static_cast<wchar_t>(0xd800 + (c >> 10)); out += static_cast<wchar_t>(0xdc00 + (c & 1023)); }
    }
    return out;
}
std::string utf8(const std::wstring& value)
{
    std::string out;
    for (size_t i = 0; i < value.size(); ++i) {
        unsigned c = value[i];
        if (c >= 0xd800 && c <= 0xdbff && i + 1 < value.size() && value[i+1] >= 0xdc00 && value[i+1] <= 0xdfff)
            c = 0x10000 + ((c-0xd800)<<10) + value[++i]-0xdc00;
        else if (c >= 0xd800 && c <= 0xdfff) c = '?';
        if (c < 128) out += static_cast<char>(c);
        else if (c < 2048) { out += static_cast<char>(0xc0|(c>>6)); out += static_cast<char>(0x80|(c&63)); }
        else if (c < 65536) { out += static_cast<char>(0xe0|(c>>12)); out += static_cast<char>(0x80|((c>>6)&63)); out += static_cast<char>(0x80|(c&63)); }
        else { out += static_cast<char>(0xf0|(c>>18)); out += static_cast<char>(0x80|((c>>12)&63)); out += static_cast<char>(0x80|((c>>6)&63)); out += static_cast<char>(0x80|(c&63)); }
    }
    return out;
}
static std::string string_field(cJSON* object, const char* field)
{
    cJSON* v = cJSON_GetObjectItemCaseSensitive(object, field);
    return cJSON_IsString(v) && v->valuestring ? v->valuestring : "";
}
static bool reasonable_text(const std::string& text)
{
    return text.size() <= 1024 && text.find('\r') == std::string::npos && text.find('\n') == std::string::npos;
}
bool parse_catalog(const std::string& json, Catalog& result, std::string& error)
{
    cJSON* root = cJSON_ParseWithLengthOpts(json.c_str(), json.size()+1, NULL, 1);
    if (!root) { error = "Invalid catalog JSON"; return false; }
    cJSON* songs = cJSON_GetObjectItemCaseSensitive(root, "projects");
    cJSON* packs = cJSON_GetObjectItemCaseSensitive(root, "packages");
    bool valid = cJSON_IsArray(songs) && cJSON_IsArray(packs) && cJSON_GetArraySize(songs) <= 10000 && cJSON_GetArraySize(packs) <= 10000;
    Catalog next;
    for (cJSON* p = valid ? songs->child : NULL; p && valid; p = p->next) {
        Song song;
        song.id = string_field(p, "id"); song.title = string_field(p, "title"); song.artist = string_field(p, "artist");
        cJSON* count = cJSON_GetObjectItemCaseSensitive(p, "packages");
        valid = hex_id(song.id, 32) && reasonable_text(song.title) && reasonable_text(song.artist) &&
            cJSON_IsNumber(count) && count->valuedouble >= 0 && count->valuedouble <= 10000;
        if (valid) { song.packages = static_cast<unsigned>(count->valuedouble); next.songs.push_back(song); }
    }
    for (cJSON* p = valid ? packs->child : NULL; p && valid; p = p->next) {
        Package pack;
        pack.id = string_field(p,"id"); pack.title = string_field(p,"title"); pack.filename = string_field(p,"filename");
        cJSON* bytes = cJSON_GetObjectItemCaseSensitive(p,"bytes");
        cJSON* contents = cJSON_GetObjectItemCaseSensitive(p,"songs");
        valid = hex_id(pack.id,64) && reasonable_text(pack.title) && pack.filename.size() <= 80 &&
            !pack.filename.empty() && pack.filename.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-") == std::string::npos &&
            cJSON_IsNumber(bytes) && bytes->valuedouble > 0 && bytes->valuedouble <= 2147483648.0 && cJSON_IsArray(contents);
        if (valid) { pack.bytes = bytes->valuedouble; pack.songs = cJSON_GetArraySize(contents); next.packages.push_back(pack); }
    }
    cJSON_Delete(root);
    if (!valid) { error = "Unsupported catalog values"; return false; }
    result = next;
    return true;
}
bool parse_pair(const std::string& json, std::string& token, std::string& error)
{
    cJSON* root = cJSON_ParseWithLengthOpts(json.c_str(), json.size()+1, NULL, 1);
    if (!root) { error = "Invalid pairing response"; return false; }
    std::string value = string_field(root,"api_token");
    bool valid = value.size() >= 32 && value.size() <= 128 && value.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") == std::string::npos;
    cJSON_Delete(root);
    if (!valid) { error = "Invalid device token"; return false; }
    token = value;
    return true;
}
static std::string json_string(cJSON* root)
{
    char* value = cJSON_PrintUnformatted(root);
    std::string result = value ? value : "";
    cJSON_free(value); cJSON_Delete(root);
    return result;
}
std::string pair_body(const std::string& code)
{
    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root,"code",code.c_str());
    cJSON_AddStringToObject(root,"name","OpenLips Xbox Client");
    return json_string(root);
}
std::string job_body(const std::string& id)
{
    cJSON* root = cJSON_CreateObject();
    cJSON* projects = cJSON_AddArrayToObject(root,"projects");
    cJSON_AddItemToArray(projects,cJSON_CreateString(id.c_str()));
    return json_string(root);
}
bool contains(const Song& song, const std::wstring& query)
{
    std::wstring text = wide(song.artist + " " + song.title), needle = query;
    for (size_t i=0;i<text.size();++i) text[i]=static_cast<wchar_t>((text[i]>=0xc0&&text[i]<=0xde&&text[i]!=0xd7)?text[i]+32:towlower(text[i]));
    for (size_t i=0;i<needle.size();++i) needle[i]=static_cast<wchar_t>((needle[i]>=0xc0&&needle[i]<=0xde&&needle[i]!=0xd7)?needle[i]+32:towlower(needle[i]));
    return text.find(needle) != std::wstring::npos;
}
bool file_hash(const std::string& path, std::string& hash, double& size)
{
    FILE* file = fopen(path.c_str(),"rb");
    if (!file) return false;
    br_sha256_context ctx; br_sha256_init(&ctx);
    unsigned char buffer[65536], digest[32]; size = 0;
    size_t length;
    while ((length=fread(buffer,1,sizeof(buffer),file)) != 0) { size+=length; br_sha256_update(&ctx,buffer,length); }
    bool valid = !ferror(file); fclose(file);
    if (!valid) return false;
    br_sha256_out(&ctx,digest);
    static const char hex[] = "0123456789abcdef";
    hash.clear();
    for (unsigned i=0;i<32;++i) { hash+=hex[digest[i]>>4];hash+=hex[digest[i]&15]; }
    return true;
}
}
