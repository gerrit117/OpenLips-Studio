from tools.analyze_x360_crash_dump import decode_ppc_instruction


def test_decode_crashing_store_instruction():
    assert decode_ppc_instruction(0x90030004, 0x82AB3284) == "stw r0,4(r3)"


def test_decode_branch_target_relative_to_instruction_address():
    assert decode_ppc_instruction(0x4BFFFEFC, 0x82AB32AC) == "b 0x82AB31A8"
