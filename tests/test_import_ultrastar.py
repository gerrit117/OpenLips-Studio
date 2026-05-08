import json
from pathlib import Path

import pytest

from tools.import_ultrastar import (
    beat_to_seconds,
    chart_to_json_payload,
    main,
    parse_ultrastar_file,
    parse_ultrastar_text,
)
from tools.write_template_chart import load_json_chart


def test_parse_ultrastar_metadata_timing_and_phrase_breaks():
    chart = parse_ultrastar_text(
        "\n".join(
            [
                "#TITLE:Unit Song",
                "#ARTIST:Unit Artist",
                "#BPM:120",
                "#GAP:500",
                ": 0 4 0 Hel",
                ": 4 4 2 lo ",
                "- 8",
                ": 16 2 -12 Bye ",
                "* 20 2 5 gold ",
                "F 24 2 5 ignored ",
                "E",
            ]
        ),
        encoding="unit-test",
    )

    payload = chart_to_json_payload(chart)

    assert chart.title == "Unit Song"
    assert chart.artist == "Unit Artist"
    assert payload["timing"]["formula"].startswith("time_seconds = GAP_ms / 1000")
    assert [note["text"] for note in payload["notes"]] == ["Hel", "lo", "Bye", "gold"]
    assert [note["end_word"] for note in payload["notes"]] == [False, True, True, True]
    assert [note["line_break_after"] for note in payload["notes"]] == [False, True, False, False]
    assert payload["notes"][0]["time"] == pytest.approx(0.5)
    assert payload["notes"][0]["length"] == pytest.approx(0.5)
    assert payload["notes"][2]["time"] == pytest.approx(2.5)
    assert payload["notes"][0]["pitch"] == 60
    assert payload["notes"][2]["pitch"] == 48
    assert any("golden note imported as a normal note" in warning for warning in payload["warnings"])
    assert any("freestyle note ignored" in warning for warning in payload["warnings"])


def test_star_single_beat_line_can_act_as_phrase_marker():
    chart = parse_ultrastar_text(
        "\n".join(
            [
                "#TITLE:Unit Song",
                "#ARTIST:Unit Artist",
                "#BPM:100",
                "#GAP:0",
                ": 0 4 0 One",
                "* 8",
                ": 12 4 0 Two ",
                "E",
            ]
        )
    )

    payload = chart_to_json_payload(chart)

    assert [note["text"] for note in payload["notes"]] == ["One", "Two"]
    assert payload["notes"][0]["line_break_after"] is True
    assert any("'*' phrase marker treated as line break" in warning for warning in payload["warnings"])


def test_importer_writes_json_compatible_with_template_loader(tmp_path):
    source = tmp_path / "song.txt"
    out = tmp_path / "song.json"
    source.write_text(
        "\n".join(
            [
                "#TITLE:Loader Song",
                "#ARTIST:Loader Artist",
                "#BPM:150",
                "#GAP:1000",
                ": 0 5 3 La ",
                "- 6",
                "E",
            ]
        ),
        encoding="utf-8",
    )

    assert main([str(source), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    chart = load_json_chart(out)

    assert payload["title"] == "Loader Song"
    assert payload["notes"][0]["time"] == pytest.approx(1.0)
    assert payload["notes"][0]["length"] == pytest.approx(0.5)
    assert payload["notes"][0]["pitch"] == 63
    assert chart.notes[0].text == "La"
    assert chart.notes[0].end_word is True
    assert chart.notes[0].line_break_after is True


def test_real_ultrastar_example_imports_when_available(tmp_path):
    examples = sorted(Path("examples/ultrastar").glob("*.txt"))
    if not examples:
        pytest.skip("local UltraStar examples are not present")
    chart = parse_ultrastar_file(examples[0])
    payload = chart_to_json_payload(chart)
    out = tmp_path / "real.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = load_json_chart(out)

    assert chart.title == "Friends"
    assert "BloodPop®" in (chart.artist or "")
    assert chart.bpm == pytest.approx(210.28)
    assert chart.gap_ms == pytest.approx(18160)
    assert len(payload["notes"]) > 200
    assert payload["notes"][0]["text"] == "I"
    assert payload["notes"][0]["time"] == pytest.approx(beat_to_seconds(17, 210.28, 18160), abs=0.000001)
    assert loaded.notes[0].pitch == payload["notes"][0]["pitch"]
