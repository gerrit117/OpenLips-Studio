#include "render.h"
#include "transport.h"
#include "cJSON.h"
#include "bearssl.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "diagnostics.h"

using namespace openlips;
namespace {
const char* appRoot=
#ifdef _XBOX
    "game:\\";
#else
    "";
#endif
const char* contentRoots[]={"","Hdd1:/Content","Hdd:/Content","Usb0:/Content","Usb1:/Content","Usb2:/Content","Mu0:/Content","Mu1:/Content"};
std::wstring tr(bool de,const wchar_t* german,const wchar_t* english){return de?german:english;}
struct Result {bool ok,encoding,ready,failed;std::string error,job,path,cover,stage;Catalog catalog;std::vector<Peer> peers;Result():ok(false),encoding(false),ready(false),failed(false){}};
struct Task {
    CRITICAL_SECTION lock;
    HANDLE thread;
    volatile LONG done;
    Progress progress;
    Server server;
    Package package;
    std::string code,project,destination;
    int kind;
    Result result;
    Task():thread(NULL),done(0),kind(0){InitializeCriticalSection(&lock);}
    ~Task(){progress.cancel=1;if(thread){WaitForSingleObject(thread,INFINITE);CloseHandle(thread);}DeleteCriticalSection(&lock);}
};
static bool catalog_request(Task& task,Result& result)
{
    std::string response;
    if(!request(task.server,"GET","/api/v1/library","",response,result.error,task.progress)||!parse_catalog(response,result.catalog,result.error))return false;
    if(!request(task.server,"GET","/api/v1/status","",response,result.error,task.progress))return false;
    cJSON* status=cJSON_Parse(response.c_str());if(!status){result.error="Invalid server status";return false;}
    result.encoding=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(status,"encoding"))!=0;cJSON_Delete(status);return true;
}
DWORD WINAPI work(LPVOID argument)
{
    Task& task=*static_cast<Task*>(argument);Result result;
    if(!network_start())result.error="Network startup failed";
    else {
        if(task.kind==0){result.peers=discover(task.progress,result.error);result.ok=result.error.empty();}
        else if(task.kind==1)result.ok=catalog_request(task,result);
        else if(task.kind==2)result.ok=catalog_request(task,result);
        else if(task.kind==3){std::string folder=std::string(appRoot)+"downloads";CreateDirectoryA(folder.c_str(),NULL);result.ok=download(task.server,task.package,folder,result.path,result.error,task.progress);if(result.ok&&!task.destination.empty())result.ok=copy_to_content(task.package,result.path,task.destination,result.error,task.progress);}
        else if(task.kind==4){std::string response;result.ok=request(task.server,"POST","/api/v1/jobs",job_body(task.project),response,result.error,task.progress);
            if(result.ok){cJSON* job=cJSON_Parse(response.c_str());cJSON* id=cJSON_GetObjectItemCaseSensitive(job,"id");if(cJSON_IsString(id)&&hex_id(id->valuestring,32))result.job=id->valuestring;else{result.ok=false;result.error="Invalid job identifier";}cJSON_Delete(job);}}
        else if(task.kind==5){std::string response;result.ok=request(task.server,"GET","/api/v1/jobs/"+task.project,"",response,result.error,task.progress);
            if(result.ok){cJSON* info=cJSON_Parse(response.c_str());cJSON* state=cJSON_GetObjectItemCaseSensitive(info,"state");cJSON* stage=cJSON_GetObjectItemCaseSensitive(info,"progress");
                if(cJSON_IsString(state)){result.ready=strcmp(state->valuestring,"ready")==0;result.failed=strcmp(state->valuestring,"failed")==0;}else result.ok=false;
                if(cJSON_IsString(stage))result.stage=stage->valuestring;cJSON_Delete(info);if(result.ready)result.ok=catalog_request(task,result);}}
        else if(task.kind==6){std::string response;result.ok=request(task.server,"GET","/api/v1/projects/"+task.project,"",response,result.error,task.progress);
            if(result.ok){cJSON* info=cJSON_Parse(response.c_str());cJSON* media=cJSON_GetObjectItemCaseSensitive(info,"media");cJSON* cover=cJSON_GetObjectItemCaseSensitive(media,"cover");
                cJSON* hash=cJSON_GetObjectItemCaseSensitive(cover,"sha256");std::string expected=cJSON_IsString(hash)?hash->valuestring:"";cJSON_Delete(info);
                if(!expected.empty()){result.ok=request(task.server,"GET","/api/v1/projects/"+task.project+"/media/cover","",result.cover,result.error,task.progress);
                    if(result.ok){br_sha256_context sha;br_sha256_init(&sha);br_sha256_update(&sha,result.cover.data(),result.cover.size());unsigned char digest[32];br_sha256_out(&sha,digest);std::string actual;const char* hex="0123456789abcdef";for(unsigned i=0;i<32;++i){actual+=hex[digest[i]>>4];actual+=hex[digest[i]&15];}if(actual!=expected){result.ok=false;result.error="Cover changed during download";}}}}}
        network_stop();
    }
    if(task.progress.cancel){result.ok=false;result.error="Cancelled";}
    EnterCriticalSection(&task.lock);task.result=result;LeaveCriticalSection(&task.lock);InterlockedExchange(&task.done,1);return 0;
}
struct App {
    Renderer renderer;Server server;Catalog catalog;Task task;
    bool de,dark,connected,encoding,editing,exit;
    int tab,selection,setting,target,editKind,peerIndex,key;
    std::wstring query,edit,status;std::string job,coverId;
    DWORD nextPoll;
    std::vector<Peer> peers;
    std::vector<size_t> visible;
    App():de(true),dark(true),connected(false),encoding(false),editing(false),exit(false),tab(0),selection(0),setting(0),target(0),editKind(0),peerIndex(0),key(0),nextPoll(0){}
    bool busy()const{return task.thread!=NULL;}
    void filter(){visible.clear();for(size_t i=0;i<catalog.songs.size();++i)if(contains(catalog.songs[i],query))visible.push_back(i);if(selection>=static_cast<int>(visible.size()))selection=0;}
    void save(){cJSON* root=cJSON_CreateObject();cJSON_AddStringToObject(root,"host",server.host.c_str());cJSON_AddNumberToObject(root,"port",server.port);
        cJSON_AddBoolToObject(root,"de",de);cJSON_AddBoolToObject(root,"dark",dark);cJSON_AddNumberToObject(root,"target",target);
        char* data=cJSON_PrintUnformatted(root);FILE* file=fopen((std::string(appRoot)+"settings.json").c_str(),"wb");if(file&&data)fwrite(data,1,strlen(data),file);if(file)fclose(file);cJSON_free(data);cJSON_Delete(root);}
    void load(){FILE* file=fopen((std::string(appRoot)+"settings.json").c_str(),"rb");if(!file)return;char data[4096];size_t count=fread(data,1,sizeof(data)-1,file);fclose(file);data[count]=0;
        cJSON* root=cJSON_Parse(data);if(!root)return;cJSON* host=cJSON_GetObjectItemCaseSensitive(root,"host");cJSON* port=cJSON_GetObjectItemCaseSensitive(root,"port");
        if(cJSON_IsString(host)&&private_ip(host->valuestring))server.host=host->valuestring;if(cJSON_IsNumber(port)&&port->valueint>0&&port->valueint<=65535)server.port=port->valueint;
        de=!cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(root,"de"));dark=!cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(root,"dark"));
        cJSON* destination=cJSON_GetObjectItemCaseSensitive(root,"target");if(cJSON_IsNumber(destination)&&destination->valueint>=0&&destination->valueint<8)target=destination->valueint;cJSON_Delete(root);}
    void start(int kind){if(busy())return;task.kind=kind;task.server=server;task.progress.cancel=0;task.progress.percent=0;task.done=0;task.result=Result();
        task.thread=CreateThread(NULL,0,work,&task,0,NULL);status=tr(de,L"Verbindung wird hergestellt …",L"Connecting …");if(!task.thread)status=tr(de,L"Auftrag konnte nicht starten",L"Could not start operation");}
    void finish(){if(!busy()||!task.done)return;WaitForSingleObject(task.thread,INFINITE);CloseHandle(task.thread);task.thread=NULL;
        Result result;EnterCriticalSection(&task.lock);result=task.result;LeaveCriticalSection(&task.lock);
        if(task.kind==6){if(task.project==coverId){if(result.ok)renderer.set_cover(result.cover);status.clear();}return;}
        if(!result.ok){status=tr(de,L"Fehler: ",L"Error: ")+wide(result.error);if(task.kind==5)job.clear();return;}
        if(task.kind==0){peers=result.peers;peerIndex=0;status=peers.empty()?tr(de,L"Keine Bibliothek gefunden",L"No library found"):tr(de,L"Bibliothek gefunden",L"Library found");if(peers.size()==1){server=peers[0].server;save();start(2);}}
        else if(task.kind==1||task.kind==2){catalog=result.catalog;encoding=result.encoding;connected=true;filter();tab=0;status=tr(de,L"Bibliothek verbunden",L"Library connected");}
        else if(task.kind==3)status=task.destination.empty()?tr(de,L"Download geprüft und gespeichert",L"Download verified and saved"):tr(de,L"DLC geprüft und kopiert; lokale Kopie bleibt erhalten",L"DLC verified and copied; local copy retained");
        else if(task.kind==4){job=result.job;status=tr(de,L"DLC-Auftrag auf dem Server gestartet",L"DLC job started on server");}
        else if(task.kind==5){nextPoll=GetTickCount()+3000;if(result.ready){job.clear();catalog=result.catalog;encoding=result.encoding;filter();tab=1;selection=0;status=tr(de,L"DLC ist bereit",L"DLC is ready");}else if(result.failed){job.clear();status=tr(de,L"DLC-Erstellung fehlgeschlagen",L"DLC build failed");}else status=wide(result.stage);}
    }
    void apply_edit(){editing=false;std::string value=utf8(edit);
        if(editKind==0){if(private_ip(value)){server.host=value;connected=false;save();}else status=tr(de,L"Bitte eine private IPv4-Adresse eingeben",L"Enter a private IPv4 address");}
        else if(editKind==1){unsigned p=static_cast<unsigned>(atoi(value.c_str()));if(p>0&&p<=65535&&value.find_first_not_of("0123456789")==std::string::npos){server.port=p;connected=false;save();}else status=tr(de,L"Ungültiger Port",L"Invalid port");}
        else if(editKind==2){query=edit;selection=0;filter();}
    }
    std::wstring keys()const{return L"1234567890qwertyuiopasdfghjkl.zxcvbnm-_ äöüß";}
    void keyboard_edit(int kind,const std::wstring& initial){if(busy())return;editKind=kind;edit=initial;editing=true;key=0;}
    void move(int delta){if(editing){key=(key+delta*10+50)%50;return;}if(busy()&&task.kind!=6&&task.kind!=5)return;if(tab==2){setting=(setting+delta+7)%7;return;}int count=tab==0?static_cast<int>(visible.size()):static_cast<int>(catalog.packages.size());if(count)selection=(selection+delta+count)%count;}
    void change_peer(int delta){if(editing){key=(key+delta+50)%50;return;}if(tab!=2||setting!=0||busy()||peers.empty())return;peerIndex=(peerIndex+delta+static_cast<int>(peers.size()))%static_cast<int>(peers.size());server=peers[peerIndex].server;connected=false;save();}
    void activate(){if(editing){
#ifdef _XBOX
        std::wstring letters=keys();if(key<static_cast<int>(letters.size())&&edit.size()<128)edit+=letters[key];else if(key==48&&!edit.empty())edit.erase(edit.size()-1);else if(key==49)apply_edit();
#else
        apply_edit();
#endif
        return;}
        if(busy())return;
        if(tab==2){if(setting==0)keyboard_edit(0,wide(server.host));else if(setting==1){wchar_t value[16];swprintf_s(value,16,L"%u",server.port);keyboard_edit(1,value);}
            else if(setting==2)start(0);else if(setting==3)start(1);
            else if(setting==4){de=!de;save();}else if(setting==5){dark=!dark;save();}else if(setting==6){target=(target+1)%8;save();}return;}
        if(!connected){tab=2;setting=0;return;}
        if(tab==0&&!visible.empty()){if(!encoding){status=tr(de,L"Dieser Server stellt fertige DLCs bereit. Downloads öffnen.",L"This server serves prepared DLCs. Open Downloads.");return;}task.project=catalog.songs[visible[selection]].id;start(4);}
        else if(tab==1&&!catalog.packages.empty()){task.package=catalog.packages[selection];task.destination=contentRoots[target];start(3);}
    }
    void back(){if(editing){editing=false;return;}if(busy()){task.progress.cancel=1;status=tr(de,L"Vorgang wird abgebrochen …",L"Cancelling …");return;}if(tab!=0){tab=0;selection=0;return;}if(!query.empty()){query.clear();filter();return;}exit=true;}
    void refresh(){if(!busy()&&connected){coverId.clear();start(2);}}
    void tick(){finish();if(!busy()&&!editing&&!job.empty()&&GetTickCount()>=nextPoll){task.project=job;start(5);return;}
        if(connected&&tab==0&&!visible.empty()){std::string selected=catalog.songs[visible[selection]].id;if(selected!=coverId){renderer.set_cover("");if(!busy()){coverId=selected;task.project=selected;start(6);}else if(task.kind==6)task.progress.cancel=1;}}}
    void draw(){Theme colors(dark);Renderer& r=renderer;r.begin(colors.background);r.rect(0,0,1280,104,colors.surface);r.logo(dark);
        r.text(302,37,tr(de,L"Bibliothek",L"Library"),colors.muted);r.text(944,37,connected?wide(server.host):tr(de,L"Nicht verbunden",L"Disconnected"),connected?colors.accent:colors.muted,264);
        const wchar_t* german[]={L"Songs",L"Downloads",L"Verbindung"};const wchar_t* english[]={L"Songs",L"Downloads",L"Connection"};float tabs[]={64,228,444};
        for(int i=0;i<3;++i){r.text(tabs[i],124,de?german[i]:english[i],tab==i?colors.text:colors.muted);if(tab==i)r.rect(tabs[i],165,i==2?148:124,3,colors.accent);}r.rect(64,168,1152,1,colors.line);
        if(tab==2){std::wstring names[]={tr(de,L"Serveradresse",L"Server address"),L"Port",tr(de,L"Bibliotheken suchen",L"Find libraries"),tr(de,L"Verbinden",L"Connect"),tr(de,L"Sprache",L"Language"),tr(de,L"Darstellung",L"Appearance"),tr(de,L"Kopierziel",L"Copy destination")};
            wchar_t port[16];swprintf_s(port,16,L"%u",server.port);std::wstring values[]={wide(server.host),port,L"",connected?tr(de,L"Verbunden",L"Connected"):L"",de?L"Deutsch":L"English",dark?tr(de,L"Dunkel",L"Dark"):tr(de,L"Hell",L"Light"),target?wide(contentRoots[target]):tr(de,L"Nur herunterladen",L"Download only")};
            for(int i=0;i<7;++i){float y=202+i*53.0f;if(setting==i)r.rect(64,y-3,736,49,colors.selected);r.text(80,y,names[i],colors.text,368);r.text(444,y,values[i],colors.muted,330);}
            r.rect(832,204,1,365,colors.line);r.text(864,207,tr(de,L"Heimnetz",L"Home network"),colors.accent,328);
            r.text(864,258,L"HTTP",colors.text,328);r.text(864,302,tr(de,L"Ohne Anmeldung",L"No sign-in"),colors.muted,328);
            if(!peers.empty())r.text(864,384,wide(peers[peerIndex].name),colors.text,328);
        } else {
            r.text(64,196,tab==0?(query.empty()?tr(de,L"Songs und Interpreten suchen",L"Search songs and artists"):query):tr(de,L"Fertige DLCs und Songpacks",L"Prepared DLCs and song packs"),colors.muted,1100);
            r.rect(64,242,1152,1,colors.line);r.rect(858,264,1,333,colors.line);
            r.text(76,254,tab==0?tr(de,L"Interpret",L"Artist"):tr(de,L"Paket",L"Package"),colors.muted,280,.85f);r.text(332,254,tab==0?tr(de,L"Titel",L"Title"):tr(de,L"Songs",L"Songs"),colors.muted,400,.85f);
            size_t count=tab==0?visible.size():catalog.packages.size();int first=selection>6?selection-6:0;
            for(int row=0;row<7&&first+row<static_cast<int>(count);++row){int index=first+row;float y=301+row*42.0f;if(index==selection)r.rect(64,y-3,760,40,colors.selected);
                if(tab==0){const Song& song=catalog.songs[visible[index]];r.text(76,y,wide(song.artist),colors.text,236,.9f);r.text(332,y,wide(song.title),colors.text,472,.9f);}
                else{const Package& package=catalog.packages[index];r.text(76,y,wide(package.title),colors.text,532,.9f);wchar_t n[24];swprintf_s(n,24,L"%u",package.songs);r.text(704,y,n,colors.muted,104,.9f);}}
            if(count==0)r.text(76,325,connected?tr(de,L"Keine Einträge",L"No entries"):tr(de,L"Bibliothek verbinden",L"Connect library"),colors.muted,716);
            if(tab==0&&!visible.empty()){const Song& song=catalog.songs[visible[selection]];r.draw_cover(890,286,312,156,colors.surface);r.text(890,457,wide(song.title),colors.text,312);r.text(890,499,wide(song.artist),colors.muted,312,.9f);
                r.text(890,546,song.packages?tr(de,L"DLC auf Server verfügbar",L"DLC available on server"):tr(de,L"Projekt auf Server",L"Project on server"),colors.accent,312,.8f);
                r.text(890,576,encoding?tr(de,L"DLC erstellen",L"Build DLC"):tr(de,L"Downloads öffnen",L"Open Downloads"),colors.text,312,.8f);}
            if(tab==1&&!catalog.packages.empty()){const Package& package=catalog.packages[selection];r.text(890,296,wide(package.title),colors.text,312);
                wchar_t size[32];swprintf_s(size,32,L"%.1f MiB",package.bytes/1048576);r.text(890,348,size,colors.muted,312);
                r.text(890,432,tr(de,L"Geprüfter Download",L"Verified download"),colors.accent,312,.85f);r.text(890,480,tr(de,L"Lokale Kopie bleibt erhalten",L"Local copy is retained"),colors.muted,312,.8f);}
        }
        if(busy()){r.rect(64,608,1152,4,colors.line);r.rect(64,608,1152*task.progress.percent/100.0f,4,colors.accent);}
        r.text(64,621,status,colors.muted,1152,.75f);r.rect(64,660,1152,1,colors.line);
        r.text(64,670,tr(de,L"A  Auswählen",L"A  Select"),colors.text,235,.8f);r.text(306,670,tr(de,L"B  Zurück",L"B  Back"),colors.text,185,.8f);
        r.text(536,670,tr(de,L"X  Aktualisieren",L"X  Refresh"),colors.text,300,.8f);r.text(872,670,tr(de,L"Y  Suche",L"Y  Search"),colors.text,200,.8f);
        if(editing){r.rect(0,0,1280,720,0xd9000000);r.rect(164,144,952,468,colors.surface);
            r.text(196,164,editKind==2?tr(de,L"Suche",L"Search"):tr(de,L"Eingabe",L"Input"),colors.text);r.text(196,222,edit,colors.accent,888);
            std::wstring letters=keys();for(int i=0;i<50;++i){float x=196+(i%10)*88.0f,y=282+(i/10)*48.0f;
                if(i==key)r.rect(x-4,y,80,40,colors.selected);
                std::wstring label=i<static_cast<int>(letters.size())?(letters[i]==L' '?tr(de,L"Leer",L"Space"):letters.substr(i,1)):i==48?L"DEL":i==49?L"OK":L"";
                r.text(x+8,y,label,colors.text,70,.8f);}
            r.text(196,554,tr(de,L"A  Auswählen       B  Abbrechen",L"A  Select       B  Cancel"),colors.text,888,.85f);}
        r.end();
    }
};
#ifndef _XBOX
App* desktopApp=NULL;
WORD desktopEvents=0;
LRESULT CALLBACK window_proc(HWND window,UINT message,WPARAM w,LPARAM l){
    if(message==WM_CLOSE){if(desktopApp)desktopApp->exit=true;return 0;}
    if(message==WM_KEYDOWN){WORD event=0;switch(w){case VK_UP:event=1;break;case VK_DOWN:event=2;break;case VK_LEFT:event=4;break;case VK_RIGHT:event=8;break;case VK_RETURN:event=0x1000;break;case VK_ESCAPE:event=0x2000;break;case 'X':event=0x4000;break;case 'Y':event=0x8000;break;case 'Q':event=0x100;break;case 'E':event=0x200;break;}desktopEvents|=event;return 0;}
    if(message==WM_CHAR&&desktopApp&&desktopApp->editing){if(w==8){if(!desktopApp->edit.empty())desktopApp->edit.erase(desktopApp->edit.size()-1);}else if(w>=32&&desktopApp->edit.size()<128)desktopApp->edit+=static_cast<wchar_t>(w);return 0;}
    return DefWindowProc(window,message,w,l);
}
#endif
int run(HWND window=NULL){startup_trace("Main entered");App app;app.load();startup_trace("Settings loaded");if(!app.renderer.initialize(window)){startup_trace("Renderer failed");return 1;}startup_trace("Renderer ready");app.start(0);
#ifndef _XBOX
    desktopApp=&app;
#endif
    WORD previous=0;DWORD repeat=0,heldSince=0;WORD held=0;
    while(!app.exit){WORD buttons=0;
#ifdef _XBOX
        XINPUT_STATE state;ZeroMemory(&state,sizeof(state));for(DWORD i=0;i<XUSER_MAX_COUNT;++i)if(XInputGetState(i,&state)==ERROR_SUCCESS){buttons=state.Gamepad.wButtons;break;}
#else
        MSG message;while(PeekMessage(&message,NULL,0,0,PM_REMOVE)){TranslateMessage(&message);DispatchMessage(&message);}
        if(GetAsyncKeyState(VK_UP)&0x8000)buttons|=1;if(GetAsyncKeyState(VK_DOWN)&0x8000)buttons|=2;
        if(GetAsyncKeyState(VK_RETURN)&0x8000)buttons|=0x1000;if(GetAsyncKeyState(VK_ESCAPE)&0x8000)buttons|=0x2000;
        if(GetAsyncKeyState('X')&0x8000)buttons|=0x4000;if(GetAsyncKeyState('Y')&0x8000)buttons|=0x8000;
        if(GetAsyncKeyState('Q')&0x8000)buttons|=0x100;if(GetAsyncKeyState('E')&0x8000)buttons|=0x200;
#endif
        WORD pressed=static_cast<WORD>(buttons&~previous);previous=buttons;DWORD now=GetTickCount();WORD direction=buttons&3;
#ifndef _XBOX
        pressed|=desktopEvents;desktopEvents=0;
#endif
        if(direction!=held){held=direction;heldSince=now;repeat=now;}else if(direction&&now-heldSince>350&&now-repeat>130){pressed|=direction;repeat=now;}
        if(pressed&1)app.move(-1);if(pressed&2)app.move(1);if(pressed&0x1000)app.activate();if(pressed&0x2000)app.back();
        if(pressed&4)app.change_peer(-1);if(pressed&8)app.change_peer(1);
        if(!app.editing){if(pressed&0x4000)app.refresh();if(pressed&0x8000&&app.tab==0)app.keyboard_edit(2,app.query);
            if((pressed&0x300)&&!app.busy()){app.tab=(app.tab+((pressed&0x100)?2:1))%3;app.selection=0;}}
        app.tick();app.draw();Sleep(1);
    }
#ifndef _XBOX
    desktopApp=NULL;
#endif
    return 0;
}
}
#ifdef _XBOX
int __cdecl main(){run();XLaunchNewImage(NULL,0);}
#else
int WINAPI WinMain(HINSTANCE instance,HINSTANCE,LPSTR,int){WNDCLASS type;ZeroMemory(&type,sizeof(type));type.lpfnWndProc=window_proc;type.hInstance=instance;type.lpszClassName=L"OpenLipsXboxPreview";type.hCursor=LoadCursor(NULL,IDC_ARROW);RegisterClass(&type);
    RECT bounds={0,0,1280,720};AdjustWindowRect(&bounds,WS_OVERLAPPEDWINDOW,FALSE);
    HWND window=CreateWindow(type.lpszClassName,L"OpenLips Xbox Client - Desktop Test",WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,bounds.right-bounds.left,bounds.bottom-bounds.top,NULL,NULL,instance,NULL);
    ShowWindow(window,SW_SHOW);int result=run(window);DestroyWindow(window);return result;}
#endif
