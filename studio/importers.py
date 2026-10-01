"""MIDI and UltraStar import adapters, independent of the graphical editor."""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
import mido

from studio.model import EditorNote, StudioProject


@dataclass
class MidiLane:
    track: int
    channel: int
    name: str
    notes: list[EditorNote]
    warnings: list[str]


@dataclass
class MidiImport:
    lanes: list[MidiLane]
    bpm: float
    key_signature: str
    warnings: list[str]


def read_midi(path):
    midi = mido.MidiFile(path)
    if midi.type == 2:
        raise ValueError("Asynchronous MIDI type 2 is not supported; export a type 0/1 file")
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMPTE MIDI timing is not supported; export PPQ timing")
    events, tempos, names = [], [(0, -1, 500000)], {}
    key = ''
    for track_index, track in enumerate(midi.tracks):
        tick = 0
        for order, msg in enumerate(track):
            tick += msg.time
            events.append((tick, track_index, order, msg))
            if msg.type == 'set_tempo':
                if msg.tempo <= 0:
                    raise ValueError("MIDI tempo must be positive")
                tempos.append((tick, track_index * 1000000 + order, msg.tempo))
            elif msg.type == 'track_name':
                names[track_index] = msg.name
            elif msg.type == 'key_signature' and not key:
                key = msg.key
    tempos.sort()
    ticks, seconds, values = [0], [0.0], [500000]
    for tick, _, tempo in tempos:
        if tick == ticks[-1]:
            values[-1] = tempo
        else:
            seconds.append(seconds[-1] + mido.tick2second(tick - ticks[-1], midi.ticks_per_beat, values[-1]))
            ticks.append(tick)
            values.append(tempo)
    def time_at(tick):
        i = bisect_right(ticks, tick) - 1
        return seconds[i] + mido.tick2second(tick - ticks[i], midi.ticks_per_beat, values[i])

    active = defaultdict(deque)
    notes = defaultdict(list)
    warnings = defaultdict(list)
    lyrics = defaultdict(list)
    final_tick = max((e[0] for e in events), default=0)
    for tick, track, _, msg in sorted(events, key=lambda e: e[:3]):
        if msg.type == 'lyrics':
            lyrics[track].append((time_at(tick), msg.text))
        if msg.type == 'control_change' and msg.control == 64:
            warnings[(track, msg.channel)].append("Sustain pedal was not extended into sung note lengths")
        if msg.type not in ('note_on', 'note_off'):
            continue
        lane = track, msg.channel
        note_key = track, msg.channel, msg.note
        if msg.type == 'note_on' and msg.velocity > 0:
            active[note_key].append(time_at(tick))
        elif active[note_key]:
            start = active[note_key].popleft()
            length = time_at(tick) - start
            if length > 0:
                notes[lane].append(EditorNote(start, length, msg.note))
            else:
                warnings[lane].append("Zero-duration note omitted")
        else:
            warnings[lane].append("Unmatched note-off omitted")
    for (track, channel, pitch), starts in active.items():
        for start in starts:
            length = time_at(final_tick) - start
            warnings[(track, channel)].append("Missing note-off: note closed at file end")
            if length > 0:
                notes[(track, channel)].append(EditorNote(start, length, pitch))
    lanes = []
    for (track, channel), lane_notes in sorted(notes.items()):
        lane_notes.sort(key=lambda n: n.time)
        lane_warnings = warnings[(track, channel)]
        end = 0.0
        for note in lane_notes:
            if note.time < end - .001:
                lane_warnings.append("Polyphonic/overlapping notes: select or edit a vocal melody before export")
            end = max(end, note.time + note.length)
        unused = list(lyrics[track])
        for note in lane_notes:
            while unused and unused[0][0] < note.time - .08:
                unused.pop(0)
            if unused and abs(unused[0][0] - note.time) < .08:
                _, note.text = unused.pop(0)
                note.end_word = note.text.endswith((' ', '\n'))
                note.line_break_after = '\n' in note.text or '\r' in note.text
                if note.text.startswith(('/', '\\')):
                    previous = lane_notes[lane_notes.index(note) - 1] if lane_notes.index(note) else None
                    if previous:
                        previous.line_break_after = True
                    note.text = note.text[1:]
                note.text = note.text.strip('\r\n ')
        if channel == 9:
            lane_warnings.append("Channel 10 is conventionally percussion, not a vocal melody")
        lanes.append(MidiLane(track, channel, names.get(track, f"Spur {track + 1}"), lane_notes,
                              list(dict.fromkeys(lane_warnings))))
    global_warnings = ["Tempo map converted to absolute seconds; editor grid uses initial BPM"] if len(values) > 1 else []
    if not lanes:
        raise ValueError("MIDI contains no positive-duration notes")
    return MidiImport(lanes, mido.tempo2bpm(values[0]), key, global_warnings)


def project_from_midi(path, imported, lane_index):
    lane = imported.lanes[lane_index]
    return StudioProject(title=Path(path).stem, bpm=imported.bpm,
                         key_signature=imported.key_signature, notes=lane.notes,
                         source=f"MIDI / {lane.name} / Kanal {lane.channel + 1}",
                         warnings=imported.warnings + lane.warnings)


def import_ultrastar(path):
    from tools.import_ultrastar import parse_ultrastar_file, chart_to_json_payload
    source = parse_ultrastar_file(Path(path))
    data = chart_to_json_payload(source)
    return StudioProject(title=source.title or Path(path).stem, artist=source.artist or '',
                         bpm=source.bpm, source='UltraStar TXT',
                         warnings=source.warnings,
                         notes=[EditorNote(**{k: n[k] for k in ('time', 'length', 'pitch', 'text',
                                               'end_word', 'line_break_after')},
                                           page_break_time=n.get('page_break_time')) for n in data['notes']])
