"""Local reference tones; no soundfont, MIDI driver or external process needed."""
import math
import struct

from PySide6.QtCore import QObject, Signal, QBuffer, QByteArray, QIODevice
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices


def pitch_frequency(pitch):
    if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
        raise ValueError('Pitch must be an integer in 0..127')
    return 440.0 * 2 ** ((pitch - 69) / 12)


def tone_pcm(pitch, seconds, rate=48000, channels=1, sample_format='int16'):
    frequency = pitch_frequency(pitch)
    if not math.isfinite(seconds) or not 0 < seconds <= 30:
        raise ValueError('Tone duration must be in 0..30 seconds')
    if not 8000 <= rate <= 192000 or not 1 <= channels <= 8:
        raise ValueError('Unsupported audio output format')
    formats = {'int16': ('h', 32767), 'int32': ('i', 2147483647),
               'float': ('f', 1), 'uint8': ('B', 127)}
    if sample_format not in formats:
        raise ValueError('Unsupported sample format')
    code, scale = formats[sample_format]
    pack = struct.Struct('<' + code * channels).pack
    count = max(2, round(rate * seconds))
    ramp = max(1, min(round(rate * .008), count // 2))
    data = bytearray()
    for index in range(count):
        # Short fades avoid clicks; the fundamental alone gives an unambiguous pitch.
        level = .3 * min(1, index / ramp, (count - 1 - index) / ramp)
        value = level * math.sin(2 * math.pi * frequency * index / rate) * scale
        value = value if sample_format == 'float' else round(value)
        if sample_format == 'uint8':
            value += 128
        data.extend(pack(*([value] * channels)))
    return bytes(data)


class TonePreview(QObject):
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sink = None
        self.buffer = None
        self.volume = .6

    def set_volume(self, value):
        self.volume = max(0, min(1, value))
        if self.sink:
            self.sink.setVolume(self.volume)

    def stop(self):
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = None
        if self.buffer:
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None

    def play(self, pitch, seconds=.6):
        self.stop()
        try:
            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                raise ValueError('No audio output device is available')
            fmt = QAudioFormat()
            fmt.setSampleRate(48000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if not device.isFormatSupported(fmt):
                fmt = device.preferredFormat()
            name = {QAudioFormat.SampleFormat.Int16: 'int16',
                    QAudioFormat.SampleFormat.Int32: 'int32',
                    QAudioFormat.SampleFormat.Float: 'float',
                    QAudioFormat.SampleFormat.UInt8: 'uint8'}[fmt.sampleFormat()]
            raw = tone_pcm(pitch, min(30, max(.02, seconds)), fmt.sampleRate(), fmt.channelCount(), name)
            self.buffer = QBuffer(self)
            self.buffer.setData(QByteArray(raw))
            self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.sink = QAudioSink(device, fmt, self)
            self.sink.setVolume(self.volume)
            self.sink.start(self.buffer)
        except Exception as error:
            self.stop()
            self.failed.emit(str(error))
