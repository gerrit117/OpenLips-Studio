#!/bin/sh
# Run after extracting the Linux release to its permanent location.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
DATA=${XDG_DATA_HOME:-"$HOME/.local/share"}
mkdir -p "$DATA/applications" "$DATA/icons/hicolor/256x256/apps"
cp "$ROOT/_internal/studio/assets/app-icon.png" "$DATA/icons/hicolor/256x256/apps/openlips-studio.png"
# Escape paths for Desktop Entry's quoted Exec syntax (not shell syntax).
EXEC=$(printf '%s' "$ROOT/OpenLipsStudio" | sed 's/\\/\\\\/g; s/"/\\"/g; s/`/\\`/g; s/\$/\\$/g')
printf '[Desktop Entry]\nType=Application\nName=OpenLips Studio\nExec="%s"\nIcon=openlips-studio\nTerminal=false\nCategories=AudioVideo;Audio;\n' "$EXEC" > "$DATA/applications/openlips-studio.desktop"
printf 'Installed desktop entry in %s\n' "$DATA/applications"
