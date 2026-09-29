"""Synthetic fixtures only; no game assets or lyrics."""
import struct
import unittest

from tools.walk_ixb_graph import Graph, GraphError


SCHEMA = b'''<Classes>
<Class Name="ixSeqCode" Size="20"><Members><Member Name="m_fTriggerTiming" Offset="8"/>
<Member Name="m_fLength" Offset="12"/><Member Name="m_iTrackIndex" Offset="16"/></Members></Class>
<Class Name="lpsMelodyMarker" Size="36" Base="1"><Members>
<Member Name="m_Tone" Offset="24"/><Member Name="m_bTilt" Offset="32"/></Members></Class>
<Class Name="TestDerivedMelody" Size="40" Base="2"/>
<Class Name="ixSequence" Size="16"><Members><Member Name="m_vpSeqCode" Offset="0"/></Members></Class>
<Class Name="ixVector&lt;ixSeqCode *&gt;" Size="16"><Members>
<Member Name="_data" Offset="0"/><Member Name="_reserve" Offset="4"/>
<Member Name="_size" Offset="8"/><Member Name="_allocator" Offset="12"/>
</Members></Class>
<Class Name="lpsLyricMarker" Size="4" Base="1"><Members><Member Name="m_pMelodyMarker" Offset="0"/></Members></Class>
</Classes>'''


def record(tag, key, payload, size=None):
    return struct.pack(">III", tag, key, len(payload) if size is None else size) + payload


def fixture(records, count=None):
    return (f'<ixb IsBigEndian="true" IsText="false" NumOfElements="{len(records) if count is None else count}">'.encode()
            + SCHEMA + b'<UriList></UriList><Objects>' + b''.join(records) + b'</Objects></ixb>')


def vector(data=22, reserve=1, size=1):
    return struct.pack(">IIII", data, reserve, size, 0)


class WalkTests(unittest.TestCase):
    def test_unaligned_raw_payload_and_embedded_closing_tag(self):
        graph = Graph(fixture([record(0, 1, b'x</Objects>'), record(2, 2, bytes(36))]))
        self.assertEqual(len(graph.records), 2)
        self.assertEqual(graph.records[1].offset, graph.records[0].payload + 11)

    def test_derived_class_not_fixed_runtime_tag(self):
        graph = Graph(fixture([record(3, 1, bytes(40))]))
        self.assertTrue(graph.is_a(graph.records[0], 'lpsMelodyMarker'))
        self.assertEqual(graph.summary()['melodies'], 1)

    def test_high_tag_bits_and_length_flag(self):
        graph = Graph(fixture([record(0x1003, 1, bytes(40), 0x80000028)]))
        self.assertEqual(graph.records[0].size, 40)
        self.assertEqual(graph.records[0].tag, 0x1003)

    def test_forward_reference_to_raw_vector_and_derived_marker(self):
        graph = Graph(fixture([record(4, 11, vector()), record(0, 22, struct.pack('>I', 33)),
                               record(3, 33, bytes(40))]))
        info, targets = graph.reference_vector(graph.ref(11), 'm_vpSeqCode', 'ixSeqCode')
        self.assertEqual(info['size'], 1)
        self.assertEqual(targets, [graph.ref(33)])

    def test_null_empty_vector(self):
        graph = Graph(fixture([record(4, 11, vector(0, 0, 0))]))
        self.assertEqual(graph.reference_vector(graph.ref(11), 'm_vpSeqCode', 'ixSeqCode')[1], [])

    def test_nonnull_empty_vector(self):
        graph = Graph(fixture([record(4, 11, vector(22, 8, 0)), record(0, 22, bytes(32))]))
        self.assertEqual(graph.summary()['graph_errors'], [])

    def test_invalid_vectors(self):
        for fields, buffer in [(vector(0), None), (vector(22, 0, 1), bytes(4)),
                               (vector(22, 2, 2), bytes(4)), (vector(99), bytes(4))]:
            with self.subTest(fields=fields):
                records = [record(4, 11, fields)]
                if buffer is not None:
                    records.append(record(0, 22, buffer))
                graph = Graph(fixture(records))
                with self.assertRaises(GraphError):
                    graph.vector(graph.ref(11), 'm_vpSeqCode')

    def test_invalid_vector_target_type(self):
        graph = Graph(fixture([record(4, 11, vector()), record(0, 22, struct.pack('>I', 11))]))
        with self.assertRaisesRegex(GraphError, 'non-ixSeqCode'):
            graph.reference_vector(graph.ref(11), 'm_vpSeqCode', 'ixSeqCode')

    def test_ownership_trace(self):
        graph = Graph(fixture([record(4, 11, vector()), record(0, 22, struct.pack('>I', 33)),
                               record(3, 33, bytes(40))]))
        summary = {'vectors': [dict(owner_key=11, member='m_vpSeqCode', data_key=22, target_keys=[33])]}
        paths = graph.trace(33, summary)['ownership_paths']
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0][0]['buffer_key'], 22)
        self.assertEqual(paths[0][0]['entry_index'], 0)
        self.assertEqual(paths[0][1]['class_name'], 'TestDerivedMelody')

    def test_null_lyric_reference_is_reported_not_assumed_invalid(self):
        graph = Graph(fixture([record(6, 1, bytes(4))]))
        self.assertEqual(graph.summary()['null_lyric_links'], [1])
        self.assertEqual(graph.summary()['graph_errors'], [])

    def test_one_byte_tag_body_is_not_a_valid_record(self):
        data = fixture([bytes([2]) + bytes(40)])
        with self.assertRaises(GraphError):
            Graph(data)

    def test_bad_framing_count_and_keys(self):
        cases = [fixture([record(9, 1, b'')]), fixture([record(0, 1, b'', 100)]),
                 fixture([record(0, 1, b'')], 2), fixture([record(0, 0, b'')]),
                 fixture([record(0, 1, b''), record(0, 1, b'')]),
                 fixture([b'\0\0']), fixture([]).replace(b'</Objects>', b'')]
        for case in cases:
            with self.subTest(case=case[-70:]), self.assertRaises(GraphError):
                Graph(case)

    def test_inheritance_cycle(self):
        data = fixture([record(3, 1, bytes(40))]).replace(b'Base="2"', b'Base="3"')
        graph = Graph(data)
        with self.assertRaises(GraphError):
            list(graph.lineage(graph.records[0]))

    def test_unsupported_endianness_and_compression(self):
        for data in [b'\x0f\xf5\x12\xed', fixture([]).replace(b'IsBigEndian="true"', b'IsBigEndian="false"')]:
            with self.assertRaises(GraphError):
                Graph(data)


if __name__ == '__main__':
    unittest.main()
