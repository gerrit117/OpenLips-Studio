"""OpenLips Song (.ols) v1: a media-free, checked native chart/lyric/cover bundle.

The magic and SHA-256 checks detect format/corruption, not trusted authorship.
An attacker can create valid checksums. Servers still validate and moderate.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import stat
import zipfile
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from tools.validate_song_pair import validate_pair

MAGIC = b"OpenLipsSong\x00\x01\r\n"
MAX_BUNDLE = 18 * 1024 * 1024
MAX_MEMBER = 8 * 1024 * 1024
MEMBERS = {"manifest.json", "chart.X360", "chart_Lyric.X360", "cover.jpg"}


@dataclass(frozen=True)
class SongBundle:
    manifest: dict
    chart: bytes
    lyric: bytes
    cover: bytes
    validation: dict


def youtube_reference(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError("Invalid YouTube reference.")
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return 'https://www.youtube.com/watch?v=' + value
    url = urlparse(value)
    if url.scheme != "https" or url.username or url.password or url.port:
        raise ValueError("YouTube references must be public HTTPS URLs without credentials or a port.")
    if url.hostname == "youtu.be":
        video = url.path.strip("/")
    elif url.hostname in ("youtube.com", "www.youtube.com") and url.path == "/watch":
        video = parse_qs(url.query).get("v", [""])[0]
    elif url.hostname in ("youtube.com", "www.youtube.com") and url.path.startswith("/shorts/"):
        video = url.path.removeprefix("/shorts/").strip("/")
    else:
        raise ValueError("Only youtube.com/watch, youtube.com/shorts or youtu.be references are accepted.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        raise ValueError("Invalid YouTube video ID.")
    return "https://www.youtube.com/watch?v=" + video


def validate_cover(data):
    from PIL import Image
    if not data.startswith(b"\xff\xd8") or len(data) > 512 * 1024:
        raise ValueError("Cover must be a native 256x256 JPEG up to 512 KiB.")
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "JPEG" or image.size != (256, 256) or image.mode != "RGB":
            raise ValueError("Cover must be a native 256x256 RGB JPEG.")
        if image.info.get("exif"):
            raise ValueError("Remove EXIF metadata before sharing the cover.")
        image.verify()


def metadata_checked(metadata):
    if not isinstance(metadata, dict) or set(metadata) != {"title", "artist", "album", "genre", "language", "family"}:
        raise ValueError("Invalid song metadata fields.")
    for key, value in metadata.items():
        maximum = 160 if key in ("title", "artist", "album") else 80
        if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise ValueError(f"Invalid metadata: {key}.")
    if not metadata["title"].strip() or not metadata["artist"].strip() or metadata["family"] not in ("og", "ls2"):
        raise ValueError("Title, artist and a supported family are required.")
    if len(metadata["language"]) > 60:
        raise ValueError("Language name is too long.")
    return dict(metadata)


def media_checked(media):
    if not isinstance(media, dict) or set(media) != {"reference_video", "duration_seconds", "offset_seconds"}:
        raise ValueError("Invalid media reference fields.")
    reference = youtube_reference(media["reference_video"])
    duration, offset = media["duration_seconds"], media["offset_seconds"]
    if duration is None and reference is None:
        raise ValueError("An exact duration is required when there is no reference video.")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 1800):
        raise ValueError("Duration must be finite and between 0 and 1800 seconds.")
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or not -600 <= offset <= 600:
        raise ValueError("Invalid media synchronization offset.")
    return {"reference_video": reference, "duration_seconds": duration, "offset_seconds": offset}


def encode_bundle(chart, lyric, cover, *, metadata, duration=None, youtube=None, offset=0):
    report = validate_pair(chart, lyric)
    validate_cover(cover)
    files = {"chart.X360": chart, "chart_Lyric.X360": lyric, "cover.jpg": cover}
    manifest = {"format": "org.openlips.song", "version": 1,
                "metadata": metadata_checked(metadata),
                "media": media_checked({"reference_video": youtube, "duration_seconds": duration, "offset_seconds": offset}),
                "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()}}
    reference = manifest['media']['reference_video']
    if reference:
        manifest['media']['reference_video'] = reference.rsplit('=', 1)[1]
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    output = io.BytesIO()
    output.write(MAGIC + hashlib.sha256(serialized).digest())
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in {"manifest.json": serialized, **files}.items():
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    result = output.getvalue()
    decode_bundle(result)
    return result


def _no_duplicates(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate manifest key.")
        values[key] = value
    return values


def decode_bundle(data: bytes) -> SongBundle:
    if len(data) > MAX_BUNDLE or not data.startswith(MAGIC) or data[len(MAGIC) + 32:len(MAGIC) + 36] != b"PK\x03\x04":
        raise ValueError("Not an OpenLips Song v1 bundle, or bundle exceeds 18 MiB.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.comment or data[-22:-18] != b'PK\x05\x06':
            raise ValueError('Archive comments and trailing payloads are not accepted.')
        infos = archive.infolist()
        if len(infos) != 4 or {item.filename for item in infos} != MEMBERS or sum(i.file_size for i in infos) > 17 * 1024 * 1024:
            raise ValueError("A song bundle must contain exactly manifest, chart, lyrics and cover.")
        files = {}
        for info in infos:
            maximum = 16384 if info.filename == "manifest.json" else (512 * 1024 if info.filename == "cover.jpg" else MAX_MEMBER)
            mode = info.external_attr >> 16
            if (info.extra or info.comment or info.file_size > maximum or info.flag_bits & 1 or info.is_dir()
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                or info.compress_type not in (zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED)
                or info.file_size / max(info.compress_size, 1) > 150):
                raise ValueError("Unsafe or unsupported ZIP member.")
            with archive.open(info) as source:
                files[info.filename] = source.read(maximum + 1)
            if len(files[info.filename]) != info.file_size:
                raise ValueError("Invalid member size.")
    raw_manifest = files.pop("manifest.json")
    if hashlib.sha256(raw_manifest).digest() != data[len(MAGIC):len(MAGIC) + 32]:
        raise ValueError("Manifest integrity check failed.")
    manifest = json.loads(raw_manifest, object_pairs_hook=_no_duplicates)
    if (not isinstance(manifest, dict) or set(manifest) != {"format", "version", "metadata", "media", "files"}
        or manifest["format"] != "org.openlips.song" or type(manifest["version"]) is not int or manifest["version"] != 1):
        raise ValueError("Unsupported song manifest.")
    manifest["metadata"] = metadata_checked(manifest["metadata"])
    manifest["media"] = media_checked(manifest["media"])
    descriptors = manifest["files"]
    if not isinstance(descriptors, dict) or set(descriptors) != set(files):
        raise ValueError("Manifest file inventory mismatch.")
    for name, content in files.items():
        expected = {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        if descriptors[name] != expected:
            raise ValueError(f"File integrity check failed: {name}.")
    validate_cover(files["cover.jpg"])
    report = validate_pair(files["chart.X360"], files["chart_Lyric.X360"])
    return SongBundle(manifest, files["chart.X360"], files["chart_Lyric.X360"], files["cover.jpg"], report)
