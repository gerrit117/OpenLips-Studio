from tools.build_minimal_ixb_pair import TEXT_PAYLOAD_POINTER, TEXT_RESOURCE_HASH, build_minimal_ixb_pair
from tools.compare_ownership_fields import analyze_ownership_fields, format_ownership_diff_report


def test_ownership_field_analysis_flags_raw_file_image_payload_pointer(tmp_path):
    pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
    lyric_path = tmp_path / "synthetic_Lyric.X360"
    lyric_path.write_bytes(pair.lyric_data)

    analysis = analyze_ownership_fields(lyric_path)
    raw_records = analysis.records_by_kind["ixRawFileImage"]

    assert raw_records
    assert raw_records[0].get("data_ptr") == TEXT_PAYLOAD_POINTER
    assert any("data_ptr is not that payload hash" in issue for issue in raw_records[0].issues)


def test_ownership_diff_report_calls_out_hash_vs_fake_pointer(tmp_path):
    pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
    real_like = bytearray(pair.lyric_data)
    synthetic_path_for_offsets = tmp_path / "synthetic_for_offsets_Lyric.X360"
    synthetic_path_for_offsets.write_bytes(pair.lyric_data)
    raw_record = analyze_ownership_fields(synthetic_path_for_offsets).records_by_kind["ixRawFileImage"][0]
    data_ptr_offset = raw_record.offset + 1 + 52
    real_like[data_ptr_offset : data_ptr_offset + 4] = TEXT_RESOURCE_HASH.to_bytes(4, "big")

    real_path = tmp_path / "real_like_Lyric.X360"
    synthetic_path = tmp_path / "synthetic_Lyric.X360"
    real_path.write_bytes(real_like)
    synthetic_path.write_bytes(pair.lyric_data)

    report = format_ownership_diff_report(
        analyze_ownership_fields(real_path),
        analyze_ownership_fields(synthetic_path),
        "synthetic",
    )

    assert "Focused IXB Ownership Field Diff" in report
    assert "SUSPECT: real RawFileImage data_ptr equals the Text payload hash" in report
    assert "Canonical raw file image records" in report
