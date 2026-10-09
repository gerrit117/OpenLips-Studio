#include "transport.h"
#include "mdns.h"
#include <map>
#include <cstdio>

namespace openlips {
struct Discovered {Peer peer;bool service,open;Discovered():service(false),open(false){}};
struct Discovery {std::map<std::string,Discovered> records;};
static int record(int,const sockaddr* from,size_t,mdns_entry_type_t,uint16_t,uint16_t type,uint16_t,uint32_t,
    const void* data,size_t size,size_t nameOffset,size_t,size_t offset,size_t length,void* context)
{
    if(from->sa_family!=AF_INET)return 0;
    char address[32];const sockaddr_in* source=reinterpret_cast<const sockaddr_in*>(from);
    unsigned ip=ntohl(source->sin_addr.s_addr);sprintf_s(address,sizeof(address),"%u.%u.%u.%u",ip>>24,(ip>>16)&255,(ip>>8)&255,ip&255);
    if(!private_ip(address))return 0;
    char name[512];mdns_string_t entry=mdns_string_extract(data,size,&nameOffset,name,sizeof(name));
    std::string key(entry.str,entry.length);size_t point=key.find("._openlips._tcp.local.");
    if(point!=32||!hex_id(key.substr(0,32),32))return 0;
    Discovery* collection=static_cast<Discovery*>(context);
    if(collection->records.size()>=128&&collection->records.find(key)==collection->records.end())return 0;
    Discovered& found=collection->records[key];found.peer.id=key.substr(0,32);found.peer.server.host=address;
    if(type==MDNS_RECORDTYPE_SRV){char host[512];mdns_record_srv_t srv=mdns_record_parse_srv(data,size,offset,length,host,sizeof(host));if(srv.port){found.peer.server.port=srv.port;found.service=true;}}
    if(type==MDNS_RECORDTYPE_TXT){mdns_record_txt_t fields[16];size_t count=mdns_record_parse_txt(data,size,offset,length,fields,16);bool protocol=false,open=false;
        for(size_t i=0;i<count;++i){std::string field(fields[i].key.str,fields[i].key.length),value(fields[i].value.str,fields[i].value.length);
            if(field=="protocol")protocol=value=="1";else if(field=="auth")open=value=="0";else if(field=="name"&&value.size()<=320)found.peer.name=value;}
        found.open=protocol&&open;
    }
    return 0;
}
std::vector<Peer> discover(Progress& progress,std::string& error)
{
    std::vector<Peer> peers;Discovery collection;int socket=mdns_socket_open_ipv4(NULL);
    if(socket<0){error="Discovery socket unavailable";return peers;}
    __declspec(align(16)) unsigned char bytes[8192];const char* service="_openlips._tcp.local.";
    int query=mdns_query_send(socket,MDNS_RECORDTYPE_PTR,service,strlen(service),bytes,sizeof(bytes),0);
    if(query<0){mdns_socket_close(socket);error="Discovery query failed";return peers;}
    DWORD start=GetTickCount();while(!progress.cancel&&GetTickCount()-start<3000){fd_set ready;FD_ZERO(&ready);FD_SET(static_cast<SOCKET>(socket),&ready);timeval wait={0,100000};
        if(select(0,&ready,NULL,NULL,&wait)>0)mdns_query_recv(socket,bytes,sizeof(bytes),record,&collection,query);}
    mdns_socket_close(socket);
    for(std::map<std::string,Discovered>::iterator p=collection.records.begin();p!=collection.records.end();++p)
        if(p->second.service&&p->second.open){if(p->second.peer.name.empty())p->second.peer.name="OpenLips Library";peers.push_back(p->second.peer);}
    return peers;
}
}
