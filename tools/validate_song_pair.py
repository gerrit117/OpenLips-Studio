"""Bounded structural validation shared by song bundles and the community server."""
from types import SimpleNamespace

from tools.walk_ixb_graph import Graph
from tools.analyze_lyric_file import compute_resource_coverages

MAX_IXB_BYTES = 8 * 1024 * 1024


def validate_pair(chart: bytes, lyric: bytes) -> dict:
    for data in (chart, lyric):
        if not data.startswith(b"<ixb") or len(data) > MAX_IXB_BYTES:
            raise ValueError("Only plain IXB files up to 8 MiB are supported.")
        objects = data.find(b"<Objects")
        if not 0 < objects <= 512 * 1024:
            raise ValueError("Missing or excessive IXB schema/header.")
    graph, lyric_graph = Graph(chart), Graph(lyric)
    if max(len(graph.records), len(lyric_graph.records)) > 100000:
        raise ValueError("IXB record count exceeds the supported limit.")
    summary = graph.summary()
    if summary["graph_errors"] or not all(summary[key] for key in ("melodies", "lyrics", "charts", "sequences")):
        raise ValueError("Chart/sequence/marker ownership is missing or unresolved.")
    markers = []
    for record in graph.records:
        if not graph.is_a(record, "lpsLyricMarker"):
            continue
        info, buffer = graph.vector(record, "m_vecLyricWordData", 20)
        if not 1 <= info["size"] <= 10000:
            raise ValueError("Invalid or unsupported LyricWordData vector.")
        for index in range(info["size"]):
            markers.append(SimpleNamespace(text_offset=graph.u32(buffer, index * 20 + 4),
                                           text_length=graph.u32(buffer, index * 20 + 8)))
    resources = []
    for image in lyric_graph.records:
        if not lyric_graph.is_a(image, "ixRawFileImage"):
            continue
        info, buffer = lyric_graph.vector(image, "m_vData", 1)
        type_info, type_buffer = lyric_graph.vector(image, "m_strTypeName", 1)
        type_name = lyric[type_buffer.payload:type_buffer.payload + type_info["size"]].rstrip(b"\0") if type_buffer else b""
        if buffer is not None and info["size"] == buffer.size and type_name == b"Text":
            resources.append(SimpleNamespace(payload_start=buffer.payload, payload_end=buffer.payload + buffer.size,
                                             payload_length=buffer.size))
    coverages = compute_resource_coverages(resources, lyric, markers)
    if not coverages:
        raise ValueError("No structurally owned Text payload found.")
    coverage = max(coverages, key=lambda item: (item.markers_in_bounds, item.resource.payload_length))
    if coverage.coverage_ratio <= .90 or coverage.markers_out_of_bounds:
        raise ValueError("LyricWordData is not fully inside a Text payload with >90% coverage.")
    resource = coverage.resource
    lyric[resource.payload_start:resource.payload_end].decode("utf-8")
    return {"melodies": summary["melodies"], "lyrics": summary["lyrics"],
            "chart_objects": len(graph.records), "lyric_objects": len(lyric_graph.records),
            "coverage": round(coverage.coverage_ratio * 100, 2), "payload_bytes": resource.payload_length}
