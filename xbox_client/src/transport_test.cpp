// Host-only harness for the identical parser, LAN and file-transfer code.
#include "transport.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace openlips;
int main(int argc,char** argv)
{
    if(argc==2&&strcmp(argv[1],"selftest")==0){
        if(!private_ip("192.168.1.2")||private_ip("8.8.8.8")||private_ip("192.168.1.256")||private_ip("192.168.1.2/secret"))return 1;
        if(utf8(wide("Gr\xc3\xbc\xc3\x9f"))!="Gr\xc3\xbc\xc3\x9f")return 2;
        Catalog catalog;std::string error;
        if(parse_catalog("{\"projects\":[{\"id\":\"../../etc\"}],\"packages\":[]}",catalog,error))return 3;
        if(!parse_catalog("{\"projects\":[],\"packages\":[]}",catalog,error))return 4;
        puts("PASS core");return 0;
    }
    if(!network_start())return 21;
    Server server;Progress progress;std::string response,error;bool ok=false;
    if(argc==2&&strcmp(argv[1],"discover")==0){std::vector<Peer> peers=discover(progress,error);ok=error.empty();for(size_t i=0;i<peers.size();++i)printf("%s %s %u\n",peers[i].id.c_str(),peers[i].server.host.c_str(),peers[i].server.port);}
    else if(argc>=4){server.host=argv[2];server.port=atoi(argv[3]);
        if(strcmp(argv[1],"request")==0&&argc==6)ok=request(server,argv[4],argv[5],"",response,error,progress);
        else if(strcmp(argv[1],"post")==0&&argc==6)ok=request(server,"POST",argv[4],argv[5],response,error,progress);
        else if(strcmp(argv[1],"download")==0&&argc==9){Package package;package.id=argv[4];package.filename=argv[5];package.bytes=atof(argv[6]);ok=download(server,package,argv[7],response,error,progress);if(ok&&strcmp(argv[8],"-")!=0)ok=copy_to_content(package,response,argv[8],error,progress);}
    }
    network_stop();if(!ok){fprintf(stderr,"%s\n",error.c_str());return 22;}if(!response.empty())puts(response.c_str());return 0;
}
