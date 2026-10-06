"""Shared media/chart preparation for one song or a multi-song DLC."""
from pathlib import Path
import secrets
import tempfile

from studio.dlc_media import bundled_tool, prepare_dlc_media, preview_lyrics
from studio.exporters import export_owned_pair, internal_chart
from studio.i18n import tr
from tools.build_dlc import MAX_ASSET_BYTES, build_package, make_manifest, make_pack_manifest


def build_projects_dlc(projects, output, progress=lambda message: None, *, pack_name=None, optimize_pages=None):
    if not projects or (pack_name is not None and not pack_name.strip()):
        raise ValueError(tr('pack.need_name'))
    if pack_name is not None and not 2 <= len(projects) <= 16:
        raise ValueError(tr('pack.count_limit'))
    if not Path(output).is_dir():
        raise ValueError(tr('export.dlc_directory'))
    from studio.page_policy import prepare_pages
    projects = [prepare_pages(p, (pack_name is not None or p.page_layout_mode == 'automatic')
                if optimize_pages is None else optimize_pages) for p in projects]
    for project in projects:
        internal_chart(project)
        if not project.artist.strip() or not project.title.strip():
            raise ValueError(tr('pack.need_metadata'))
        if not Path(project.video_path or project.audio_path).is_file():
            raise ValueError(tr('export.need_media'))
    backend = bundled_tool('openlips_stfs')
    if not backend:
        raise ValueError(tr('export.missing_backend'))
    with tempfile.TemporaryDirectory(prefix='openlips-dlc-') as temp:
        root = Path(temp)
        files, songs = {}, []
        pack_id = 0x03000000 | secrets.randbits(24)
        for index, project in enumerate(projects):
            progress(tr('pack.preparing', index=index + 1, count=len(projects), title=project.title))
            folder = root / f'song{index:02d}'
            folder.mkdir()
            def report(message):
                with (folder / 'conversion.log').open('a', encoding='utf-8') as stream:
                    stream.write(message + '\n')
            media, duration = prepare_dlc_media(project, folder / 'media', report)
            if project.duration > duration + .5:
                raise ValueError(tr('export.notes_past_media'))
            name = f'song{index:02d}' if pack_name is not None else 'custom'
            if pack_name is not None:
                for key, path in list(media.items()):
                    target = path.with_name(f'{name}_{key}{path.suffix}')
                    path.rename(target)
                    media[key] = target
            pair = export_owned_pair(project, folder / 'pair', name, media['audio'].stem,
                media['video'].stem if 'video' in media else None, duration=duration)
            assets = {key: path.name for key, path in media.items()}
            files.update({path.name: path for path in media.values()})
            for key, filename in (('chart', name + '.X360'), ('lyric', name + '_Lyric.X360')):
                assets[key], files[filename] = filename, pair / filename
            if sum(path.stat().st_size for path in files.values()) > MAX_ASSET_BYTES:
                raise ValueError(tr('pack.size_limit'))
            song_id = (pack_id | (index << 28)) if pack_name is not None else 0x73000000 | secrets.randbits(24)
            songs.append(dict(title=project.title, artist=project.artist,
                              uint_id=song_id, duration=duration, assets=assets,
                              preview_lyric=preview_lyrics(project)))
        manifest = make_pack_manifest(songs, pack_id) if pack_name is not None else make_manifest(
            songs[0]['title'], songs[0]['artist'], songs[0]['uint_id'], songs[0]['duration'], songs[0]['assets'],
            preview_lyric=songs[0]['preview_lyric'])
        progress(tr('export.packaging'))
        return build_package(backend, files, manifest, output, pack_name or projects[0].title,
                             canonical_name=True)
