import struct

import pytest

from tools.build_lyric_resource import (
    ASSET_PACKAGE, CHILD_NODE, IMAGE, NAME, ROOT, TEXT, build_lyric_ixb, validate_lyric_ownership,
)
from tools.walk_ixb_graph import Graph, GraphError


@pytest.mark.parametrize("family,package_size,asset_offset", [("og", 52, 52), ("later", 72, 72)])
def test_synthetic_lyric_uses_most_derived_asset_and_real_lists(family, package_size, asset_offset):
    data = build_lyric_ixb("Demo_Lyric", b"\xef\xbb\xbf\r\nHi there\r\n", family=family)
    graph = Graph(data)
    summary = validate_lyric_ownership(data)
    assert summary["records"] == 12
    assert summary["classes"]["ixRawFileImage"] == 1
    assert summary["classes"]["ixDblCnt<ixPackage *>"] == 3
    assert "ixAsset" not in summary["classes"]
    assert "ixFileImage" not in summary["classes"]
    assert summary["classes"]["ixPackage"] == 1
    package = graph.ref(ASSET_PACKAGE)
    assert package.size == package_size + 20
    assert graph.members(package)["m_vpAssets"] == asset_offset
    assert graph.ref(TEXT).class_index == 0


def test_equal_names_have_independently_owned_buffers():
    data = bytearray(build_lyric_ixb("Demo_Lyric", b"Hi"))
    graph = Graph(data)
    root = graph.ref(ROOT)
    assert graph.u32(root, 24) != graph.u32(graph.ref(IMAGE), 8)
    struct.pack_into(">I", data, root.payload + 24, NAME)
    with pytest.raises(GraphError, match="share/null"):
        validate_lyric_ownership(bytes(data))


def test_lyric_validator_rejects_broken_list_reference():
    data = bytearray(build_lyric_ixb("Demo_Lyric", b"Hi"))
    node = Graph(data).ref(CHILD_NODE)
    struct.pack_into(">I", data, node.payload + 4, 0)
    with pytest.raises(GraphError, match="child-list"):
        validate_lyric_ownership(bytes(data))


def test_lyric_builder_preserves_exact_utf8_payload():
    payload = "\ufeff\r\nGruesse </Objects>\r\n".encode("utf-8")
    data = build_lyric_ixb("Demo_Lyric", payload)
    graph = Graph(data)
    text = graph.ref(TEXT)
    assert data[text.payload:text.payload + text.size] == payload
    assert data == build_lyric_ixb("Demo_Lyric", payload)
