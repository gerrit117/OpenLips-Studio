// Open LAN transport: no credentials, certificate checks or public endpoints.
#include "transport.h"
#include "bearssl.h"
#include "diagnostics.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace openlips {
bool network_start()
{
#ifdef _XBOX
    XNetStartupParams params;ZeroMemory(&params,sizeof(params));params.cfgSizeOfStruct=sizeof(params);params.cfgFlags=XNET_STARTUP_BYPASS_SECURITY;
    if(XNetStartup(&params)!=0)return false;
#endif
    WSADATA data;return WSAStartup(MAKEWORD(2,2),&data)==0;
}
void network_stop(){WSACleanup();
#ifdef _XBOX
    XNetCleanup();
#endif
}
struct Connection {
    SOCKET socket;Progress* progress;DWORD started,maximum;
    Connection():socket(INVALID_SOCKET),progress(NULL),started(GetTickCount()),maximum(120000){}
    ~Connection(){if(socket!=INVALID_SOCKET)closesocket(socket);}
    int receive(char* bytes,size_t size){if(progress->cancel||GetTickCount()-started>maximum)return -1;return recv(socket,bytes,static_cast<int>(size),0);}
    bool receive_all(char* bytes,size_t size){while(size){int count=receive(bytes,size);if(count<=0)return false;bytes+=count;size-=count;}return true;}
    bool send_all(const std::string& bytes){size_t sent=0;while(sent<bytes.size()&&!progress->cancel){int count=send(socket,bytes.data()+sent,static_cast<int>(bytes.size()-sent),0);if(count<=0)return false;sent+=count;}return sent==bytes.size();}
};
static bool connect(Connection& connection,const Server& server,Progress& progress,std::string& error)
{
    bool local=false;
#ifdef OPENLIPS_HOST_TEST
    local=true;
#endif
    if(!private_ip(server.host,local)||!server.port||server.port>65535){error="Use a private IPv4 address and valid port";return false;}
    connection.progress=&progress;connection.socket=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    if(connection.socket==INVALID_SOCKET){error="Socket unavailable";return false;}
#ifdef _XBOX
    // Retail XNet ignores the devkit startup bypass. Each LAN socket also
    // needs the homebrew plaintext options before connecting to a PC.
    BOOL plaintext=TRUE;
    if(setsockopt(connection.socket,SOL_SOCKET,0x5801,reinterpret_cast<const char*>(&plaintext),sizeof(plaintext))==SOCKET_ERROR ||
       setsockopt(connection.socket,SOL_SOCKET,0x5802,reinterpret_cast<const char*>(&plaintext),sizeof(plaintext))==SOCKET_ERROR){
        long code=WSAGetLastError();startup_trace("LAN socket options",code);
        char message[96];sprintf_s(message,sizeof(message),"LAN socket setup failed (WSA %ld)",code);error=message;return false;
    }
#endif
    DWORD timeout=10000;setsockopt(connection.socket,SOL_SOCKET,SO_RCVTIMEO,reinterpret_cast<const char*>(&timeout),sizeof(timeout));setsockopt(connection.socket,SOL_SOCKET,SO_SNDTIMEO,reinterpret_cast<const char*>(&timeout),sizeof(timeout));
    u_long nonblocking=1;ioctlsocket(connection.socket,FIONBIO,&nonblocking);
    sockaddr_in address;ZeroMemory(&address,sizeof(address));address.sin_family=AF_INET;address.sin_port=htons(static_cast<u_short>(server.port));address.sin_addr.s_addr=inet_addr(server.host.c_str());
    if(::connect(connection.socket,reinterpret_cast<sockaddr*>(&address),sizeof(address))==SOCKET_ERROR){
        int code=WSAGetLastError();startup_trace("LAN connect",code);
        if(code!=WSAEWOULDBLOCK&&code!=WSAEINPROGRESS){char message[96];sprintf_s(message,sizeof(message),"Library connect failed (WSA %d)",code);error=message;return false;}
        fd_set writable,failed;FD_ZERO(&writable);FD_ZERO(&failed);FD_SET(connection.socket,&writable);FD_SET(connection.socket,&failed);timeval wait={8,0};
        int ready=select(0,NULL,&writable,&failed,&wait);int reason=ready==0?WSAETIMEDOUT:0;
#ifndef _XBOX
        int size=sizeof(reason);if(ready>0&&getsockopt(connection.socket,SOL_SOCKET,SO_ERROR,reinterpret_cast<char*>(&reason),&size)==SOCKET_ERROR)reason=WSAGetLastError();
#endif
        if(ready<=0||FD_ISSET(connection.socket,&failed)||reason){
            char message[128];sprintf_s(message,sizeof(message),"Library unreachable: %s:%u (WSA %d)",server.host.c_str(),server.port,reason?reason:WSAGetLastError());error=message;startup_trace("LAN connect failed",reason);return false;
        }
    }
    nonblocking=0;ioctlsocket(connection.socket,FIONBIO,&nonblocking);return true;
}
static bool begin_request(Connection& connection,const Server& server,const std::string& method,const std::string& endpoint,
    const std::string& body,unsigned& status,double& length,std::string& error,Progress& progress)
{
    if((method!="GET"&&method!="POST")||endpoint.find("/api/v1/")!=0||endpoint.find_first_of("\r\n ")!=std::string::npos||body.size()>8192){error="Invalid request";return false;}
    if(!connect(connection,server,progress,error))return false;
    char port[16],size[32];sprintf_s(port,sizeof(port),"%u",server.port);sprintf_s(size,sizeof(size),"%u",static_cast<unsigned>(body.size()));
    std::string headers=method+" "+endpoint+" HTTP/1.1\r\nHost: "+server.host+":"+port+"\r\nConnection: close\r\n";
    if(method=="POST")headers+="Content-Type: application/json\r\nContent-Length: "+std::string(size)+"\r\n";
    headers+="\r\n";headers+=body;if(!connection.send_all(headers)){error="Request failed";return false;}
    std::string raw;while(raw.size()<16384&&(raw.size()<4||raw.substr(raw.size()-4)!="\r\n\r\n")){char byte;if(!connection.receive_all(&byte,1)){error="Incomplete HTTP headers";return false;}raw+=byte;}
    if(raw.size()>=16384||raw.find("HTTP/1.")!=0){error="Invalid HTTP headers";return false;}
    status=static_cast<unsigned>(atoi(raw.c_str()+9));length=-1;size_t offset=raw.find("\r\n")+2;bool found=false;
    while(offset<raw.size()-2){size_t end=raw.find("\r\n",offset);std::string line=raw.substr(offset,end-offset);for(size_t i=0;i<line.size();++i)if(line[i]>='A'&&line[i]<='Z')line[i]+='a'-'A';
        if(line.find("content-length:")==0){if(found){error="Duplicate content length";return false;}found=true;const char* number=line.c_str()+15;while(*number==' ')++number;if(!*number){error="Missing length";return false;}length=0;for(;*number;++number){if(*number<'0'||*number>'9'||length>2147483648.0){error="Invalid length";return false;}length=length*10+*number-'0';}}
        if(line.find("transfer-encoding:")==0){error="Unsupported HTTP transfer encoding";return false;}offset=end+2;
    }
    if(length<0||length>2147483648.0){error="Invalid response size";return false;}return true;
}
bool request(const Server& server,const std::string& method,const std::string& endpoint,const std::string& body,
    std::string& response,std::string& error,Progress& progress)
{
    Connection connection;unsigned status;double length;
    if(!begin_request(connection,server,method,endpoint,body,status,length,error,progress))return false;
    if(length>4*1024*1024){error="Response exceeds 4 MiB";return false;}response.assign(static_cast<size_t>(length),'\0');
    if(length&&!connection.receive_all(&response[0],static_cast<size_t>(length))){error="Incomplete response";return false;}
    if(status<200||status>=300){char code[32];sprintf_s(code,sizeof(code),"HTTP %u",status);error=code;return false;}return true;
}
bool download(const Server& server,const Package& package,const std::string& directory,std::string& path,std::string& error,Progress& progress)
{
    if(!hex_id(package.id,64)||package.bytes<=0||package.bytes>2147483648.0||package.filename.size()!=42||package.filename.find_first_not_of("0123456789ABCDEF")!=std::string::npos){error="Invalid package metadata";return false;}
    path=directory+"/"+package.filename;std::string digest;double size;
    if(file_hash(path,digest,size)){if(digest==package.id&&size==package.bytes){progress.percent=100;return true;}error="Existing file differs; not overwritten";return false;}
    Connection connection;unsigned status;double length;if(!begin_request(connection,server,"GET","/api/v1/packages/"+package.id,"",status,length,error,progress))return false;
    if(status!=200||length!=package.bytes){error="Package response size/status mismatch";return false;}connection.maximum=3600000;
    std::string temporary=directory+"/"+package.id.substr(0,32)+".tmp";
    HANDLE file=CreateFileA(temporary.c_str(),GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);if(file==INVALID_HANDLE_VALUE){error="Cannot create a new temporary download";return false;}
    br_sha256_context ctx;br_sha256_init(&ctx);char bytes[32768];double received=0;bool valid=true;
    while(received<length&&!progress.cancel){size_t wanted=static_cast<size_t>(length-received);if(wanted>sizeof(bytes))wanted=sizeof(bytes);int count=connection.receive(bytes,wanted);DWORD written=0;if(count<=0||!WriteFile(file,bytes,count,&written,NULL)||written!=static_cast<DWORD>(count)){valid=false;break;}br_sha256_update(&ctx,bytes,count);received+=count;progress.percent=static_cast<LONG>(received*100/length);}
    valid=valid&&received==length&&!progress.cancel;if(valid)valid=FlushFileBuffers(file)!=FALSE;CloseHandle(file);
    if(valid){unsigned char hash[32];br_sha256_out(&ctx,hash);static const char hex[]="0123456789abcdef";digest.clear();for(unsigned i=0;i<32;++i){digest+=hex[hash[i]>>4];digest+=hex[hash[i]&15];}valid=digest==package.id;}
    if(valid)valid=MoveFileA(temporary.c_str(),path.c_str())!=FALSE;if(!valid){DeleteFileA(temporary.c_str());error=progress.cancel?"Download cancelled":"Package integrity or publishing failed";return false;}progress.percent=100;return true;
}
bool copy_to_content(const Package& package,const std::string& source,const std::string& root,std::string& error,Progress& progress)
{
#ifndef OPENLIPS_HOST_TEST
    const char* roots[]={"Hdd1:/Content","Hdd:/Content","Usb0:/Content","Usb1:/Content","Usb2:/Content","Mu0:/Content","Mu1:/Content"};bool allowed=false;for(unsigned i=0;i<7;++i)if(root==roots[i])allowed=true;if(!allowed){error="Unsupported Content root";return false;}
#endif
    DWORD attributes=GetFileAttributesA(root.c_str());if(attributes==static_cast<DWORD>(-1)||!(attributes&FILE_ATTRIBUTE_DIRECTORY)){error="Content folder is not available";return false;}
    if(package.filename.size()!=42||package.filename.find_first_not_of("0123456789ABCDEF")!=std::string::npos){error="Invalid Xbox filename";return false;}
    FILE* input=fopen(source.c_str(),"rb");if(!input){error="Prepared download is missing";return false;}unsigned char header[0x364];bool valid=fread(header,1,sizeof(header),input)==sizeof(header)&&memcmp(header,"LIVE",4)==0&&header[0x344]==0&&header[0x345]==0&&header[0x346]==0&&header[0x347]==2&&header[0x360]==0x4d&&header[0x361]==0x53&&header[0x362]==0x08&&header[0x363]==0x88;fclose(input);if(!valid){error="Not a Lips LIVE package";return false;}
    std::string folder=root;const char* parts[]={"0000000000000000","4D530888","00000002"};for(unsigned i=0;i<3;++i){folder+="/";folder+=parts[i];if(!CreateDirectoryA(folder.c_str(),NULL)&&GetLastError()!=ERROR_ALREADY_EXISTS){error="Cannot prepare Content folder";return false;}}
    std::string target=folder+"/"+package.filename,digest;double size;if(file_hash(target,digest,size)){if(digest==package.id&&size==package.bytes)return true;error="An existing installed package differs; not overwritten";return false;}
    std::string staging=root+"/.openlips-transfer";if(!CreateDirectoryA(staging.c_str(),NULL)&&GetLastError()!=ERROR_ALREADY_EXISTS){error="Cannot prepare staging folder";return false;}
    std::string temporary=staging+"/"+package.id.substr(0,32)+".tmp";input=fopen(source.c_str(),"rb");if(!input){error="Download is unavailable";return false;}HANDLE output=CreateFileA(temporary.c_str(),GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);if(output==INVALID_HANDLE_VALUE){fclose(input);error="Cannot create a new staging file";return false;}
    unsigned char buffer[32768];size_t count;double transferred=0;valid=true;while(!progress.cancel&&(count=fread(buffer,1,sizeof(buffer),input))!=0){DWORD written=0;if(!WriteFile(output,buffer,static_cast<DWORD>(count),&written,NULL)||written!=count){valid=false;break;}transferred+=count;progress.percent=static_cast<LONG>(transferred*100/package.bytes);}
    valid=valid&&!ferror(input)&&!progress.cancel&&transferred==package.bytes;fclose(input);if(valid)valid=FlushFileBuffers(output)!=FALSE;CloseHandle(output);if(valid)valid=file_hash(temporary,digest,size)&&digest==package.id&&size==package.bytes;if(valid)valid=MoveFileA(temporary.c_str(),target.c_str())!=FALSE;if(!valid){DeleteFileA(temporary.c_str());error="Copy cancelled or integrity check failed";return false;}return true;
}
}
