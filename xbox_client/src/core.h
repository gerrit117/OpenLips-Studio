#pragma once
#include <string>
#include <vector>

namespace openlips {
struct Server {
    std::string host;
    unsigned port;
    Server() : host("192.168.1.100"), port(8765) {}
};
struct Peer {Server server;std::string id,name;};
struct Song {
    std::string id, title, artist;
    unsigned packages;
    Song() : packages(0) {}
};
struct Package {
    std::string id, filename, title;
    double bytes;
    unsigned songs;
    Package() : bytes(0), songs(0) {}
};
struct Catalog {
    std::vector<Song> songs;
    std::vector<Package> packages;
};
bool private_ip(const std::string& host, bool loopback = false);
bool hex_id(const std::string& value, size_t length);
std::wstring wide(const std::string& value);
std::string utf8(const std::wstring& value);
bool parse_catalog(const std::string& json, Catalog& result, std::string& error);
bool parse_pair(const std::string& json, std::string& token, std::string& error);
std::string pair_body(const std::string& code);
std::string job_body(const std::string& id);
bool contains(const Song& song, const std::wstring& query);
bool file_hash(const std::string& path, std::string& hash, double& size);
}
