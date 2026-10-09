#pragma once
#ifdef _XBOX
#include <xtl.h>
#else
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d9.h>
#endif
#include <string>
#include <vector>

namespace openlips {
struct Theme {
    DWORD background, surface, text, muted, line, accent, selected, danger;
    Theme(bool dark=true);
};
class Renderer {
    IDirect3D9* graphics;
    IDirect3DDevice9* device;
    IDirect3DVertexShader9* vertexShader;
    IDirect3DPixelShader9* pixelShader;
    IDirect3DVertexDeclaration9* declaration;
    IDirect3DTexture9 *white, *font, *logoDark, *logoLight, *cover;
    unsigned coverWidth,coverHeight;
    float advances[512];
    void quad(IDirect3DTexture9* texture,float x,float y,float w,float h,DWORD color,float u=0,float v=0,float uw=1,float vh=1);
    IDirect3DTexture9* asset(const char* path,bool fontAsset);
public:
    Renderer();
    ~Renderer();
    bool initialize(HWND window=NULL);
    void begin(DWORD background);
    void end();
    void rect(float x,float y,float w,float h,DWORD color);
    void text(float x,float y,const std::wstring& value,DWORD color,float maxWidth=0,float scale=1);
    void logo(bool dark);
    void set_cover(const std::string& bytes);
    void draw_cover(float x,float y,float width,float height,DWORD background);
};
}
