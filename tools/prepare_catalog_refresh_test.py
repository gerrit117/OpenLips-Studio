"""Prepare opt-in OG Lua experiments; never install or repack game files."""

import argparse
import hashlib
import json
from pathlib import Path

SUPPORTED_SHA256 = 'ad5c505828ab0c7bf9c78b0b91ac73e83e1698d4d8f487be446c8234e6227819'
SENTINEL = b'-- OpenLips catalog refresh experiment'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hook(mode, frames=30):
    if mode not in ('observe', 'coalesce'):
        raise ValueError('Unknown experiment mode')
    if not 1 <= frames <= 120:
        raise ValueError('Batch window must be 1..120 menu updates')
    # Use the existing state callback, not an unverified timer or DLC-end event.
    return f'''
-- OpenLips catalog refresh experiment (unverified in retail)
do
    local state = PlayMenu2.Play
    local installed = state.OnMusicIndexInstalled
    local evaluate = state.EvalState
    local selected = state.OnSelectCompleted
    local leaving = PlayMenu2.OnLeaveState
    local optimize = {'true' if mode == 'coalesce' else 'false'}
    local frame, events, refreshes, selections = 0, 0, 0, 0
    local pending, due, sender = false, 0, nil
    local function summary(reason)
        print("OPENLIPS_CATALOG mode={mode} reason=" .. reason ..
            " frame=" .. frame .. " events=" .. events ..
            " refreshes=" .. refreshes .. " selections=" .. selections)
    end
    local function refresh(self, source)
        if PlayMenu2.bActivePlayMenu and
            not PlayMenu2Properties.bChallengeEnumeration then
            refreshes = refreshes + 1
        end
        return installed(self, source)
    end
    local function flush(self)
        if pending then
            local source = sender
            pending, sender = false, nil
            refresh(self, source)
            summary("flush")
        end
    end
    function state:OnMusicIndexInstalled(source)
        events = events + 1
        if events == 1 or events % 100 == 0 then summary("event") end
        if optimize and PlayMenu2.bActivePlayMenu and
            not PlayMenu2Properties.bChallengeEnumeration then
            if not pending then due = frame + {frames} end
            pending, sender = true, source
            PlayMenu2.bChangedMusicList = true
            return
        end
        return refresh(self, source)
    end
    function state:EvalState(...)
        frame = frame + 1
        if pending and frame >= due then flush(self) end
        return evaluate(self, ...)
    end
    function state:OnSelectCompleted(...)
        selections = selections + 1
        return selected(self, ...)
    end
    function PlayMenu2:OnLeaveState(...)
        -- No queued update is abandoned when the menu state stops ticking.
        flush(state)
        summary("leave")
        return leaving(self, ...)
    end
    summary("hook_active")
end
'''.encode('ascii')


def prepare(source, output, frames=30):
    data = source.read_bytes()
    if digest(data) != SUPPORTED_SHA256:
        raise ValueError('Unsupported PlayMenu2.lua hash; no files written')
    observe = data + hook('observe', frames)
    coalesce = data + hook('coalesce', frames)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        'source_sha256': digest(data), 'source_size': len(data),
        'status': 'prepared_not_installed_runtime_unverified',
        'window_menu_updates': frames,
        'files': {},
    }
    for name, content in [('original.lua', data), ('observe.lua', observe),
                          ('coalesce.lua', coalesce)]:
        (output / name).write_bytes(content)
        manifest['files'][name] = digest(content)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def restore(bundle, target):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    original = (bundle / 'original.lua').read_bytes()
    if digest(original) != manifest['source_sha256']:
        raise ValueError('Original backup hash mismatch')
    current = target.read_bytes()
    if digest(current) not in manifest['files'].values():
        raise ValueError('Target changed independently; refusing rollback')
    # Rollback is explicit; preserve the current candidate alongside the target.
    backup = target.with_name(target.name + '.before-rollback')
    with backup.open('xb') as stream:
        stream.write(current)
    target.write_bytes(original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('prepare')
    build.add_argument('source', type=Path)
    build.add_argument('--out', type=Path, required=True)
    build.add_argument('--window-frames', type=int, default=30)
    rollback = commands.add_parser('rollback')
    rollback.add_argument('bundle', type=Path)
    rollback.add_argument('target', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(args.source, args.out, args.window_frames), indent=2))
        print('NOT INSTALLED: retail packed-script execution must be verified.')
    else:
        restore(args.bundle, args.target)
        print('Original restored; previous candidate preserved beside target.')


if __name__ == '__main__':
    main()
