// Local SDK bring-up probe. No networking, installs or game-file changes.
#include <xtl.h>
#include <xui.h>

static void label(HXUIDC dc, HXUIFONT font, float y, const WCHAR* value, DWORD color)
{
    XUIRect bounds(72.0f, y, 1208.0f, y + 48.0f);
    XuiSelectFont(dc, font);
    XuiSetColorFactor(dc, color);
    XuiDrawText(dc, value, XUI_FONT_STYLE_SINGLE_LINE, 0, &bounds);
}

int __cdecl main()
{
    OutputDebugStringA("OpenLips probe: entry\n");
    IDirect3D9* graphics = Direct3DCreate9(D3D_SDK_VERSION);
    if (!graphics) return 1;
    D3DPRESENT_PARAMETERS parameters;
    ZeroMemory(&parameters, sizeof(parameters));
    parameters.BackBufferWidth = 1280;
    parameters.BackBufferHeight = 720;
    parameters.BackBufferFormat = D3DFMT_A8R8G8B8;
    parameters.BackBufferCount = 1;
    parameters.SwapEffect = D3DSWAPEFFECT_DISCARD;
    parameters.PresentationInterval = D3DPRESENT_INTERVAL_ONE;
    IDirect3DDevice9* device = NULL;
    if (FAILED(graphics->CreateDevice(0, D3DDEVTYPE_HAL, NULL,
            D3DCREATE_HARDWARE_VERTEXPROCESSING, &parameters, &device))) {
        graphics->Release();
        return 2;
    }
    XUIInitParams ui;
    XUI_INIT_PARAMS(ui);
    if (FAILED(XuiInit(&ui))) return 3;
    if (FAILED(XuiRenderInitShared(device, &parameters, XuiPNGTextureLoader))) return 4;
    HXUIDC dc = NULL;
    if (FAILED(XuiRenderCreateDC(&dc))) return 5;
    TypefaceDescriptor typeface;
    ZeroMemory(&typeface, sizeof(typeface));
    typeface.szTypeface = L"OpenLips Probe";
    typeface.szLocator = L"file://game:/media/client.ttf";
    HXUIFONT font = NULL;
    if (FAILED(XuiRegisterTypeface(&typeface, TRUE)) ||
        FAILED(XuiCreateFont(typeface.szTypeface, 24.0f, XUI_FONT_STYLE_NORMAL, 0, &font))) return 6;
    OutputDebugStringA("OpenLips probe: graphics and text ready\n");
    WORD previous = 0;
    bool alternate = false;
    DWORD activePad = XUSER_MAX_COUNT;
    for (;;) {
        XINPUT_STATE state;
        ZeroMemory(&state, sizeof(state));
        activePad = XUSER_MAX_COUNT;
        for (DWORD pad = 0; pad < XUSER_MAX_COUNT; ++pad) {
            if (XInputGetState(pad, &state) == ERROR_SUCCESS) {
                activePad = pad;
                break;
            }
        }
        WORD buttons = activePad < XUSER_MAX_COUNT ? state.Gamepad.wButtons : 0;
        WORD pressed = static_cast<WORD>(buttons & ~previous);
        previous = buttons;
        if (pressed & XINPUT_GAMEPAD_A) {
            alternate = !alternate;
            OutputDebugStringA("OpenLips probe: A pressed\n");
        }
        if (pressed & XINPUT_GAMEPAD_B) break;
        if (FAILED(XuiRenderBegin(dc, alternate ? 0xff203c3b : 0xff151a1e))) break;
        label(dc, font, 72, L"OpenLips - Xbox Client", 0xffefefef);
        label(dc, font, 148, L"SDK start / controller test", 0xff31b6ad);
        label(dc, font, 244, activePad < XUSER_MAX_COUNT ? L"Controller connected" : L"Connect a controller", 0xffefefef);
        label(dc, font, 328, alternate ? L"A received: alternate view" : L"A: switch background", 0xffefefef);
        label(dc, font, 412, L"B: return to dashboard", 0xffefefef);
        label(dc, font, 572, L"Probe only - no downloads or installation", 0xffa1adb5);
        XuiRenderEnd(dc);
        XuiRenderPresent(dc, NULL, NULL, NULL);
    }
    OutputDebugStringA("OpenLips probe: exit\n");
    XuiReleaseFont(font);
    XuiRenderDestroyDC(dc);
    XuiRenderUninit();
    XuiUninit();
    device->Release();
    graphics->Release();
    XLaunchNewImage(NULL, 0);
}
