from tools.build_minimal_ixb_pair import TEXT_PAYLOAD_POINTER, TEXT_RESOURCE_HASH, build_minimal_ixb_pair
from tools.compare_ownership_fields import analyze_ownership_fields, format_ownership_corpus_report, format_ownership_diff_report


def test_ownership_field_analysis_flags_raw_file_image_payload_pointer(tmp_path):
    pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
    lyric_path = tmp_path / "synthetic_Lyric.X360"
    lyric_path.write_bytes(pair.lyric_data)

    analysis = analyze_ownership_fields(lyric_path)
    raw_records = analysis.records_by_kind["ixRawFileImage"]

    assert raw_records
    assert raw_records[0].get("data_ptr") == TEXT_RESOURCE_HASH
    assert raw_records[0].get("data_reserve") == len(pair.lyric_text.encode("utf-8"))
    assert raw_records[0].get("data_size") == len(pair.lyric_text.encode("utf-8"))
    assert not any("data_ptr is not that payload hash" in issue for issue in raw_records[0].issues)


def test_ownership_diff_report_calls_out_hash_vs_fake_pointer(tmp_path):
    pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
    broken_synthetic = bytearray(pair.lyric_data)
    real_path = tmp_path / "real_like_Lyric.X360"
    broken_path = tmp_path / "broken_synthetic_Lyric.X360"
    real_path.write_bytes(pair.lyric_data)
    raw_record = analyze_ownership_fields(real_path).records_by_kind["ixRawFileImage"][0]
    data_ptr_offset = raw_record.offset + 1 + 52
    broken_synthetic[data_ptr_offset : data_ptr_offset + 4] = TEXT_PAYLOAD_POINTER.to_bytes(4, "big")

    broken_path.write_bytes(broken_synthetic)

    report = format_ownership_diff_report(
        analyze_ownership_fields(real_path),
        analyze_ownership_fields(broken_path),
        "synthetic",
    )

    assert "Focused IXB Ownership Field Diff" in report
    assert "SUSPECT: real RawFileImage data_ptr equals the Text payload hash" in report
    assert "Canonical raw file image records" in report


def test_ownership_corpus_report_includes_frequencies(tmp_path):
    for name in ("one_Lyric.X360", "two_Lyric.X360"):
        pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
        (tmp_path / name).write_bytes(pair.lyric_data)

    report = format_ownership_corpus_report([tmp_path])

    assert "Lyric samples analyzed: 2" in report
    assert "ixRawFileImage.data_ptr equals a Text payload hash: 2/2 confidence=high" in report
    assert "all Text resources use compact type header pointer/length/inline Text: 2/2 confidence=high" in report
