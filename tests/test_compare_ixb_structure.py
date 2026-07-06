from pathlib import Path

from tools.build_minimal_ixb_pair import build_minimal_ixb_pair
from tools.compare_ixb_structure import format_pair_comparison, summarize_ixb_file


def test_synthetic_summary_reports_marker_tags_and_text_coverage(tmp_path: Path):
    pair = build_minimal_ixb_pair()
    chart_path = tmp_path / "Tiny.X360"
    lyric_path = tmp_path / "Tiny_Lyric.X360"
    chart_path.write_bytes(pair.chart_data)
    lyric_path.write_bytes(pair.lyric_data)

    chart = summarize_ixb_file(chart_path, label="synthetic chart", role="chart")
    lyric = summarize_ixb_file(lyric_path, label="synthetic lyric", role="lyric", linked_chart_data=pair.chart_data)

    assert chart.melody_count == len(pair.notes)
    assert chart.lyric_count == len(pair.notes)
    assert chart.melody_prefix_counts[0x28] == len(pair.notes)
    assert chart.lyric_prefix_counts[0x40] == len(pair.notes)
    assert lyric.text_selection is not None
    assert lyric.text_selection.resource_count == 1
    assert lyric.text_selection.coverage_in_bounds == len(pair.notes)
    assert lyric.text_selection.coverage_total == len(pair.notes)
    assert chart.is_big_endian is True
    assert chart.is_text is False
    assert chart.platform == "WIN32"
    assert chart.uri_count == 0
    assert chart.write_order_warnings == ()
    assert chart.object_record_candidate_count >= 0
    assert chart.fileio_header_candidate_count >= 0
    assert lyric.is_big_endian is True
    assert lyric.platform == "WIN32"
    assert lyric.object_record_candidate_count >= 0
    assert lyric.fileio_header_candidate_count >= 0


def test_pair_comparison_names_minimal_resource_chain(tmp_path: Path):
    pair = build_minimal_ixb_pair()
    chart_path = tmp_path / "Tiny.X360"
    lyric_path = tmp_path / "Tiny_Lyric.X360"
    chart_path.write_bytes(pair.chart_data)
    lyric_path.write_bytes(pair.lyric_data)

    chart = summarize_ixb_file(chart_path, label="synthetic chart", role="chart")
    lyric = summarize_ixb_file(lyric_path, label="synthetic lyric", role="lyric", linked_chart_data=pair.chart_data)
    report = format_pair_comparison(chart, lyric, chart, lyric)

    assert "Marker Record Tagging" in report
    assert "Writer-Oriented Metadata" in report
    assert "IsBigEndian=True" in report
    assert "UriList entries=0" in report
    assert "Minimum Next Structures To Model" in report
    assert "synthetic lyric resource chain is still minimal" in report
