// SPDX-License-Identifier: GPL-3.0-or-later
// Thin adapter for Velocity's STFS writer; no Microsoft signing keys or SDK.
#include "Stfs/StfsPackage.h"
#include <filesystem>
#include <fstream>
#include <codecvt>
#include <locale>
#include <algorithm>

namespace fs = std::filesystem;

static std::wstring wide(const char* value) {
    return std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>>().from_bytes(value);
}

static void check_name(const std::string& name) {
    if (name.empty() || name.size() > 40 || name == "." || name == ".." ||
        name.find_first_of("/\\:\r\n") != std::string::npos ||
        std::any_of(name.begin(), name.end(), [](unsigned char c) {return c < 32 || c > 126;}))
        throw std::runtime_error("only flat ASCII STFS filenames of 1-40 bytes are supported");
}

static int run(int argc, char** argv) {
    try {
        if (argc == 4 && std::string(argv[1]) == "extract") {
            if (fs::exists(argv[3])) throw std::runtime_error("extraction directory exists");
            StfsPackage p(argv[2]);
            auto listing = p.GetFileListing();
            if (!listing.folderEntries.empty()) throw std::runtime_error("only flat packages supported");
            fs::create_directories(argv[3]);
            for (auto& file : listing.fileEntries) {
                check_name(file.name);
                p.ExtractFile(file.name, (fs::path(argv[3])/file.name).string());
            }
            p.Close();
            return 0;
        }
        if (argc != 6 || std::string(argv[1]) != "build")
            throw std::runtime_error("usage: build DIRECTORY OUTPUT TITLE_ID DISPLAY_NAME | extract PACKAGE NEW_DIRECTORY");
        if (fs::exists(argv[3])) throw std::runtime_error("output exists");
        std::vector<fs::path> files;
        UINT64 content_size = 0;
        for (auto& entry : fs::directory_iterator(argv[2])) {
            if (entry.is_symlink() || !entry.is_regular_file()) throw std::runtime_error("staging must contain regular flat files only");
            check_name(entry.path().filename().string());
            files.push_back(entry.path());
            content_size += entry.file_size();
        }
        if (files.empty()) throw std::runtime_error("staging is empty");
        std::sort(files.begin(), files.end());
        StfsPackage p(argv[3], StfsPackageCreate | StfsPackageFemale);
        auto& m = *p.metaData;
        m.magic = LIVE;
        std::fill_n(m.packageSignature, sizeof(m.packageSignature), 0);
        m.contentType = MarketPlaceContent;
        m.titleID = std::stoul(argv[4], nullptr, 16);
        m.platform = 2;
        m.displayName = wide(argv[5]);
        m.displayDescription = L"OpenLips custom song; unsigned research package";
        m.publisherName = L"OpenLips";
        m.titleName = L"Lips";
        m.contentSize = content_size;
        m.licenseData[0].bits = 7;
        m.licenseData[0].flags = 1;
        m.WriteMetaData();
        for (auto& file : files) p.InjectFile(file.string(), file.filename().string());
        p.Rehash();
        p.Close();
        // The library initially created a CON header. Clear its certificate
        // region before publishing the unsigned LIVE header, avoiding stale data.
        std::fstream header(argv[3], std::ios::in|std::ios::out|std::ios::binary);
        header.seekp(4);
        std::vector<char> zeros(0x228, 0);
        header.write(zeros.data(), zeros.size());
        header.close();
        std::cout << "unsigned LIVE STFS; files=" << files.size() << " payload_bytes=" << content_size << "\n";
        return 0;
    } catch (const std::string& error) {
        std::cerr << error << "\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
    }
    return 1;
}

int wmain(int argc, wchar_t** wide_argv) {
    std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> convert;
    std::vector<std::string> storage;
    for (int i = 0; i < argc; ++i) storage.push_back(convert.to_bytes(wide_argv[i]));
    std::vector<char*> args;
    for (auto& value : storage) args.push_back(value.data());
    return run(argc, args.data());
}
