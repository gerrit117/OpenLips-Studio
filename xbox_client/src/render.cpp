#include "render.h"
#include "render_vertex.h"
#include "render_pixel.h"
#include <cstdio>
#include <cstring>
#include "diagnostics.h"
#define STB_IMAGE_IMPLEMENTATION
#define STBI_NO_SIMD
#define STBI_NO_HDR
#define STBI_NO_LINEAR
#define STBI_MAX_DIMENSIONS 2048
#include "stb_image.h"

namespace openlips {
Theme::Theme(bool dark)
{
    background=dark?0xff111618:0xfffafcfc;surface=dark?0xff25292e:0xffeef2f3;
    text=dark?0xffe9eff0:0xff20272c;muted=dark?0xffa1afb4:0xff647079;
    line=dark?0xff344045:0xffdce2e5;accent=dark?0xff61ccc5:0xff087f7f;
    selected=dark?0xff203b3b:0xffe5f4f2;danger=dark?0xffef8b97:0xffac343f;
}
Renderer::Renderer() : graphics(NULL),device(NULL),vertexShader(NULL),pixelShader(NULL),declaration(NULL),white(NULL),font(NULL),logoDark(NULL),logoLight(NULL),cover(NULL),coverWidth(0),coverHeight(0)
{ZeroMemory(advances,sizeof(advances));}
Renderer::~Renderer()
{
    if(cover)cover->Release();if(logoLight)logoLight->Release();if(logoDark)logoDark->Release();if(font)font->Release();if(white)white->Release();
    if(declaration)declaration->Release();if(pixelShader)pixelShader->Release();if(vertexShader)vertexShader->Release();
    if(device)device->Release();if(graphics)graphics->Release();
}
static unsigned big32(const unsigned char* bytes){return (bytes[0]<<24)|(bytes[1]<<16)|(bytes[2]<<8)|bytes[3];}
IDirect3DTexture9* Renderer::asset(const char* path,bool fontAsset)
{
    FILE* file=fopen(path,"rb");if(!file){startup_trace(path,-1);return NULL;}
    unsigned char header[8];if(fread(header,1,8,file)!=8){fclose(file);return NULL;}
    unsigned width=big32(header),height=big32(header+4);
    if(!width||!height||width>2048||height>2048){fclose(file);return NULL;}
    if(fontAsset){unsigned char metrics[512*4];if(fread(metrics,1,sizeof(metrics),file)!=sizeof(metrics)){fclose(file);return NULL;}
        for(unsigned i=0;i<512;++i)advances[i]=big32(metrics+i*4)/64.0f;}
    IDirect3DTexture9* texture=NULL;
#ifdef _XBOX
    D3DFORMAT format=D3DFMT_LIN_A8R8G8B8;D3DPOOL pool=D3DPOOL_DEFAULT;
#else
    D3DFORMAT format=D3DFMT_A8R8G8B8;D3DPOOL pool=D3DPOOL_MANAGED;
#endif
    if(FAILED(device->CreateTexture(width,height,1,0,format,pool,&texture,NULL))){fclose(file);return NULL;}
    D3DLOCKED_RECT lock;if(FAILED(texture->LockRect(0,&lock,NULL,0))){texture->Release();fclose(file);return NULL;}
    std::vector<unsigned char> row(width*4);bool valid=true;
    for(unsigned y=0;y<height;++y){if(fread(&row[0],1,row.size(),file)!=row.size()){valid=false;break;}
        DWORD* pixels=reinterpret_cast<DWORD*>(static_cast<unsigned char*>(lock.pBits)+y*lock.Pitch);
        for(unsigned x=0;x<width;++x)pixels[x]=(row[x*4+3]<<24)|(row[x*4]<<16)|(row[x*4+1]<<8)|row[x*4+2];}
    texture->UnlockRect(0);fclose(file);if(!valid){texture->Release();return NULL;}return texture;
}
bool Renderer::initialize(HWND window)
{
    startup_trace("Renderer initialize");
    graphics=Direct3DCreate9(D3D_SDK_VERSION);if(!graphics){startup_trace("Direct3DCreate9",-1);return false;}
    D3DPRESENT_PARAMETERS pp;ZeroMemory(&pp,sizeof(pp));pp.BackBufferWidth=1280;pp.BackBufferHeight=720;
    pp.BackBufferFormat=D3DFMT_A8R8G8B8;pp.BackBufferCount=1;pp.SwapEffect=D3DSWAPEFFECT_DISCARD;
    pp.PresentationInterval=D3DPRESENT_INTERVAL_ONE;
#ifndef _XBOX
    pp.Windowed=TRUE;pp.hDeviceWindow=window;pp.BackBufferFormat=D3DFMT_UNKNOWN;
#endif
    HRESULT hr=graphics->CreateDevice(0,D3DDEVTYPE_HAL,window,D3DCREATE_HARDWARE_VERTEXPROCESSING,&pp,&device);
    startup_trace("CreateDevice",hr);if(FAILED(hr))return false;
    hr=device->CreateVertexShader(reinterpret_cast<const DWORD*>(render_vertex),&vertexShader);
    startup_trace("CreateVertexShader",hr);if(FAILED(hr))return false;
    hr=device->CreatePixelShader(reinterpret_cast<const DWORD*>(render_pixel),&pixelShader);
    startup_trace("CreatePixelShader",hr);if(FAILED(hr))return false;
    D3DVERTEXELEMENT9 elements[]={{0,0,D3DDECLTYPE_FLOAT2,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_POSITION,0},
        {0,8,D3DDECLTYPE_FLOAT2,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_TEXCOORD,0},
        {0,16,D3DDECLTYPE_FLOAT4,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_COLOR,0},D3DDECL_END()};
    hr=device->CreateVertexDeclaration(elements,&declaration);
    startup_trace("CreateVertexDeclaration",hr);if(FAILED(hr))return false;
#ifdef _XBOX
    D3DFORMAT format=D3DFMT_LIN_A8R8G8B8;D3DPOOL pool=D3DPOOL_DEFAULT;
#else
    D3DFORMAT format=D3DFMT_A8R8G8B8;D3DPOOL pool=D3DPOOL_MANAGED;
#endif
    hr=device->CreateTexture(1,1,1,0,format,pool,&white,NULL);
    startup_trace("White texture",hr);if(FAILED(hr))return false;
    D3DLOCKED_RECT lock;hr=white->LockRect(0,&lock,NULL,0);
    startup_trace("White texture lock",hr);if(FAILED(hr))return false;
    *static_cast<DWORD*>(lock.pBits)=0xffffffff;white->UnlockRect(0);
#ifdef _XBOX
    font=asset("game:\\media\\font.raw",true);logoDark=asset("game:\\media\\logo-dark.raw",false);logoLight=asset("game:\\media\\logo-light.raw",false);
#else
    font=asset("media/font.raw",true);logoDark=asset("media/logo-dark.raw",false);logoLight=asset("media/logo-light.raw",false);
#endif
    startup_trace("Font asset",font?0:-1);startup_trace("Dark logo asset",logoDark?0:-1);startup_trace("Light logo asset",logoLight?0:-1);
    return font&&logoDark&&logoLight;
}
void Renderer::begin(DWORD background)
{
    device->Clear(0,NULL,D3DCLEAR_TARGET,background,1,0);device->BeginScene();
    device->SetVertexShader(vertexShader);device->SetPixelShader(pixelShader);device->SetVertexDeclaration(declaration);
    device->SetRenderState(D3DRS_ZENABLE,FALSE);device->SetRenderState(D3DRS_CULLMODE,D3DCULL_NONE);
    device->SetRenderState(D3DRS_ALPHABLENDENABLE,TRUE);device->SetRenderState(D3DRS_SRCBLEND,D3DBLEND_SRCALPHA);
    device->SetRenderState(D3DRS_DESTBLEND,D3DBLEND_INVSRCALPHA);
    device->SetSamplerState(0,D3DSAMP_MINFILTER,D3DTEXF_LINEAR);device->SetSamplerState(0,D3DSAMP_MAGFILTER,D3DTEXF_LINEAR);
    device->SetSamplerState(0,D3DSAMP_ADDRESSU,D3DTADDRESS_CLAMP);device->SetSamplerState(0,D3DSAMP_ADDRESSV,D3DTADDRESS_CLAMP);
}
void Renderer::end(){device->EndScene();device->Present(NULL,NULL,NULL,NULL);}
void Renderer::quad(IDirect3DTexture9* texture,float x,float y,float w,float h,DWORD color,float u,float v,float uw,float vh)
{
    struct Vertex {float x,y,u,v,r,g,b,a;};
    float r=((color>>16)&255)/255.0f,g=((color>>8)&255)/255.0f,b=(color&255)/255.0f,a=(color>>24)/255.0f;
    __declspec(align(16)) Vertex vertices[]={{x,y,u,v,r,g,b,a},{x+w,y,u+uw,v,r,g,b,a},{x,y+h,u,v+vh,r,g,b,a},
        {x+w,y,u+uw,v,r,g,b,a},{x+w,y+h,u+uw,v+vh,r,g,b,a},{x,y+h,u,v+vh,r,g,b,a}};
    device->SetTexture(0,texture);device->DrawPrimitiveUP(D3DPT_TRIANGLELIST,2,vertices,sizeof(Vertex));
}
void Renderer::rect(float x,float y,float w,float h,DWORD color){quad(white,x,y,w,h,color);}
static unsigned glyph(wchar_t character){if(character>=32&&character<=255)return character-32;if(character>=0x400&&character<=0x4ff)return 224+character-0x400;return '?'-32;}
void Renderer::text(float x,float y,const std::wstring& value,DWORD color,float maxWidth,float scale)
{
    float origin=x;
    for(size_t i=0;i<value.size();++i){unsigned index=glyph(value[i]);float step=advances[index]*scale;
        if(maxWidth>0&&x-origin+step>maxWidth){for(int n=0;n<3;++n){unsigned dot='.'-32;float d=advances[dot]*scale;if(x-origin+d>maxWidth)break;quad(font,x,y,32*scale,40*scale,color,(dot%32)/32.0f,(dot/32)/16.0f,1/32.0f,1/16.0f);x+=d;}break;}
        quad(font,x,y,32*scale,40*scale,color,(index%32)/32.0f,(index/32)/16.0f,1/32.0f,1/16.0f);x+=step;}
}
void Renderer::logo(bool dark){quad(dark?logoDark:logoLight,52,13,224,93,0xffffffff);}
void Renderer::set_cover(const std::string& bytes)
{
    if(cover){cover->Release();cover=NULL;}coverWidth=coverHeight=0;
    if(bytes.empty()||bytes.size()>4*1024*1024)return;
    int width,height,channels;
    if(!stbi_info_from_memory(reinterpret_cast<const stbi_uc*>(bytes.data()),static_cast<int>(bytes.size()),&width,&height,&channels)||width<=0||height<=0||width>2048||height>2048)return;
    stbi_uc* rgba=stbi_load_from_memory(reinterpret_cast<const stbi_uc*>(bytes.data()),static_cast<int>(bytes.size()),&width,&height,&channels,4);if(!rgba)return;
#ifdef _XBOX
    D3DFORMAT format=D3DFMT_LIN_A8R8G8B8;D3DPOOL pool=D3DPOOL_DEFAULT;
#else
    D3DFORMAT format=D3DFMT_A8R8G8B8;D3DPOOL pool=D3DPOOL_MANAGED;
#endif
    if(SUCCEEDED(device->CreateTexture(width,height,1,0,format,pool,&cover,NULL))){D3DLOCKED_RECT lock;if(SUCCEEDED(cover->LockRect(0,&lock,NULL,0))){
        for(int y=0;y<height;++y){DWORD* pixels=reinterpret_cast<DWORD*>(static_cast<unsigned char*>(lock.pBits)+y*lock.Pitch);for(int x=0;x<width;++x){unsigned char* p=rgba+(y*width+x)*4;pixels[x]=(p[3]<<24)|(p[0]<<16)|(p[1]<<8)|p[2];}}
        cover->UnlockRect(0);coverWidth=width;coverHeight=height;}else{cover->Release();cover=NULL;}}
    stbi_image_free(rgba);
}
void Renderer::draw_cover(float x,float y,float width,float height,DWORD background)
{
    if(!cover){rect(x+(width-height)/2,y,height,height,background);return;}
    float factor=width/coverWidth;if(coverHeight*factor>height)factor=height/coverHeight;
    float w=coverWidth*factor,h=coverHeight*factor;quad(cover,x+(width-w)/2,y+(height-h)/2,w,h,0xffffffff);
}
}
