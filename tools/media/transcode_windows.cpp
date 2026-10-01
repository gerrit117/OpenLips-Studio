// Experimental native Windows ASF conversion. No Xbox SDK is required.
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mferror.h>
#include <wrl/client.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
using Microsoft::WRL::ComPtr;

static void check(HRESULT hr, const char* operation) {
    if (FAILED(hr)) {
        std::cerr << operation << " HRESULT=0x" << std::hex << static_cast<unsigned long>(hr) << "\n";
        throw std::runtime_error(operation);
    }
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 3 || argc > 4 || (argc == 4 && std::wstring(argv[3]) != L"--audio-only")) {
        std::cerr << "usage: transcode_windows input new-output.wmv [--audio-only]\n";
        return 2;
    }
    const bool audio_only = argc == 4;
    const auto output = std::filesystem::absolute(argv[2]);
    const auto temporary = output.wstring() + L".partial.wmv";
    if (std::filesystem::exists(output) || std::filesystem::exists(temporary)) {
        std::cerr << "output or partial file exists; refusing to overwrite\n";
        return 2;
    }
    bool com = false, mf = false;
    ComPtr<IMFMediaSession> session;
    ComPtr<IMFMediaSource> source;
    int result = 1;
    try {
        check(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "CoInitializeEx");
        com = true;
        check(MFStartup(MF_VERSION), "MFStartup");
        mf = true;
        ComPtr<IMFSourceResolver> resolver;
        check(MFCreateSourceResolver(&resolver), "source resolver");
        ComPtr<IUnknown> object;
        MF_OBJECT_TYPE kind;
        check(resolver->CreateObjectFromURL(argv[1], MF_RESOLUTION_MEDIASOURCE, nullptr,
                                           &kind, &object), "open input");
        check(object.As(&source), "media source");
        ComPtr<IMFTranscodeProfile> profile;
        check(MFCreateTranscodeProfile(&profile), "transcode profile");
        ComPtr<IMFCollection> types;
        check(MFTranscodeGetAudioOutputAvailableTypes(MFAudioFormat_WMAudioV9,
              MFT_ENUM_FLAG_SYNCMFT | MFT_ENUM_FLAG_LOCALMFT | MFT_ENUM_FLAG_SORTANDFILTER,
              nullptr, &types), "enumerate WMA Pro types");
        DWORD count = 0;
        check(types->GetElementCount(&count), "audio type count");
        ComPtr<IMFMediaType> selected;
        for (DWORD i = 0; i < count; ++i) {
            ComPtr<IUnknown> entry;
            ComPtr<IMFMediaType> type;
            check(types->GetElement(i, &entry), "audio type");
            check(entry.As(&type), "audio media type");
            UINT32 rate = 0, channels = 0, bytes = 0, bits = 0;
            type->GetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, &rate);
            type->GetUINT32(MF_MT_AUDIO_NUM_CHANNELS, &channels);
            type->GetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, &bytes);
            type->GetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, &bits);
            if (rate == 48000 && channels == 2 && bytes == 24000 && bits == 16) {
                selected = type;
                std::cout << "audio: 48000 Hz stereo 192000 bit/s, 16-bit WMA Pro\n";
                break;
            }
        }
        if (!selected) throw std::runtime_error("48k stereo 192k 16-bit WMA Pro encoder type unavailable");
        check(profile->SetAudioAttributes(selected.Get()), "audio profile");
        if (!audio_only) {
        ComPtr<IMFAttributes> video;
        check(MFCreateAttributes(&video, 8), "video attributes");
        check(video->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video), "video major");
        check(video->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_WVC1), "VC-1 subtype");
        check(MFSetAttributeSize(video.Get(), MF_MT_FRAME_SIZE, 768, 432), "video size");
        check(MFSetAttributeRatio(video.Get(), MF_MT_FRAME_RATE, 24000, 1001), "video rate");
        check(MFSetAttributeRatio(video.Get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1), "pixel aspect");
        check(video->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive), "interlace");
        check(video->SetUINT32(MF_MT_AVG_BITRATE, 2000000), "video bitrate");
        check(profile->SetVideoAttributes(video.Get()), "video profile");
        }
        ComPtr<IMFAttributes> container;
        check(MFCreateAttributes(&container, 2), "container attributes");
        check(container->SetGUID(MF_TRANSCODE_CONTAINERTYPE, MFTranscodeContainerType_ASF), "ASF container");
        check(container->SetUINT32(MF_TRANSCODE_ADJUST_PROFILE, MF_TRANSCODE_ADJUST_PROFILE_DEFAULT), "profile policy");
        check(profile->SetContainerAttributes(container.Get()), "container profile");
        ComPtr<IMFTopology> topology;
        check(MFCreateTranscodeTopology(source.Get(), temporary.c_str(), profile.Get(), &topology), "transcode topology");
        check(MFCreateMediaSession(nullptr, &session), "media session");
        check(session->SetTopology(0, topology.Get()), "set topology");
        bool closing = false;
        for (;;) {
            ComPtr<IMFMediaEvent> event;
            check(session->GetEvent(0, &event), "session event");
            HRESULT status;
            check(event->GetStatus(&status), "event status");
            check(status, "asynchronous encoding");
            MediaEventType type;
            check(event->GetType(&type), "event type");
            std::cout << "event=" << type << std::endl;
            if (type == MESessionTopologyStatus) {
                UINT32 state = 0;
                check(event->GetUINT32(MF_EVENT_TOPOLOGY_STATUS, &state), "topology status");
                if (state == MF_TOPOSTATUS_READY) {
                    PROPVARIANT start;
                    PropVariantInit(&start);
                    check(session->Start(&GUID_NULL, &start), "start encoding");
                }
            } else if (type == MESessionEnded && !closing) {
                check(session->Close(), "close encoding session");
                closing = true;
            } else if (type == MESessionClosed) break;
        }
        session->Shutdown();
        session.Reset();
        source->Shutdown();
        source.Reset();
        // MoveFile refuses an existing destination, including one created meanwhile.
        if (!MoveFileW(temporary.c_str(), output.c_str()))
            check(HRESULT_FROM_WIN32(GetLastError()), "publish output");
        std::cout << (audio_only ? "encoded audio-only WMA Pro ASF\n" : "encoded VC-1 / WMA Pro ASF at 768x432\n");
        result = 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
    }
    if (session) session->Shutdown();
    if (source) source->Shutdown();
    session.Reset();
    source.Reset();
    if (mf) MFShutdown();
    if (com) CoUninitialize();
    if (result && std::filesystem::exists(temporary)) std::filesystem::remove(temporary);
    return result;
}
