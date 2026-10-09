#pragma once
#include "core.h"
#ifdef _XBOX
#include <xtl.h>
#else
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#endif

namespace openlips {
struct Progress {
    volatile LONG cancel, percent;
    Progress() : cancel(0), percent(0) {}
};
bool network_start();
void network_stop();
std::vector<Peer> discover(Progress& progress,std::string& error);
bool request(const Server& server, const std::string& method, const std::string& endpoint,
    const std::string& body, std::string& response, std::string& error, Progress& progress);
bool download(const Server& server, const Package& package, const std::string& directory,
    std::string& path, std::string& error, Progress& progress);
bool copy_to_content(const Package& package,const std::string& source,const std::string& root,
    std::string& error,Progress& progress);
}
