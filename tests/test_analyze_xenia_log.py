from tools.analyze_xenia_log import analyze_lines, format_report


SYNTHETIC_LOG = """\
i> 00000001 Build: canary / abcdef0 on Sep 17 2026
  XEX_HEADER_ORIGINAL_PE_NAME: LPS_X360_Release_LTCG.exe
       Title ID: 4D530888
d> 00000028 XMPGetMediaSources(00000002, 00000001, 40001000, 0000000A, 40002000), unimplemented
!> 00000028 Unimplemented XMP message app=000000FA, msg=00070044, arg1=40000000, arg2=00000010
d> 00000098 SetThreadName(13, AudioCapture0)
d> 00000098 XamUserGetDeviceContext(00000000, 00000004, 4065FC40(00000000))
E> 00000098 MicDeviceRequest State: 00000001 Action: 0007 USER: 00000000
d> 00000028 XamContentCreate(00000000)
!> 00000028 ==== CRASH DUMP ====
!> 00000028 PC: 0x82CFE920
!> 00000028  r1   = 000000004018F780
!> 00000028  r3   = 00000000EAE76200
"""


def test_analyze_lips_runtime_signals():
    analysis = analyze_lines(SYNTHETIC_LOG.splitlines())

    assert analysis.build.startswith("canary / abcdef0")
    assert analysis.title_id == "4D530888"
    assert analysis.original_pe_name == "LPS_X360_Release_LTCG.exe"
    assert analysis.xmp_calls["XMPGetMediaSources"] == 1
    assert analysis.unimplemented_xmp["00070044"] == 1
    assert analysis.device_context_classes[4] == 1
    assert analysis.device_context_users[0] == 1
    assert analysis.mic_requests[(1, 7, 0)] == 1
    assert analysis.audio_capture_threads["AudioCapture0"] == 1
    assert analysis.content_calls["XamContentCreate"] == 1
    assert analysis.crashes[0].pc == "0x82CFE920"
    assert analysis.crashes[0].registers["r1"] == "0x000000004018F780"


def test_report_explains_xmp_before_microphone():
    report = format_report(analyze_lines(SYNTHETIC_LOG.splitlines()))

    assert "title_id: 4D530888" in report
    assert "unimplemented_xmp: 00070044=1" in report
    assert "device class 4 (microphone)" in report
    assert "current Canary" in report
