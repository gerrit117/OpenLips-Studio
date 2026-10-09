#!/bin/bash
# Run on the Unraid host. Never stop/recreate the container or change its mounts.
set -euo pipefail
container="${1:-}"
if [[ ! "$container" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo 'Usage: bash recover-template.sh EXACT-CONTAINER-NAME' >&2
  exit 1
fi
directory=/boot/config/plugins/dockerMan/templates-user
[[ -d /boot/config ]] || { echo 'Run this on the Unraid host.' >&2; exit 1; }
mkdir -p "$directory"
work=$(mktemp -d)
trap 'rm -f "$work/recover.py" "$work/template.xml"; rmdir "$work"' EXIT
curl --fail --location --connect-timeout 15 --max-time 60 \
  https://raw.githubusercontent.com/gerrit117/OpenLips-Studio/main/library_server/unraid/recover_template.py \
  -o "$work/recover.py"
OPENLIPS_INSPECT=$(docker inspect "$container")
export OPENLIPS_INSPECT
docker exec -i -e OPENLIPS_INSPECT "$container" python - < "$work/recover.py" > "$work/template.xml"
[[ -s "$work/template.xml" ]] || { echo 'No template generated.' >&2; exit 1; }
target="$directory/my-$container.xml"
if [[ -L "$target" ]]; then echo 'Refusing a symlink template.' >&2; exit 1; fi
if [[ -e "$target" ]]; then
  cp -p -- "$target" "$target.backup-$(date +%Y%m%d-%H%M%S)"
fi
install -m 600 "$work/template.xml" "$target"
echo "Saved $target. Refresh Docker, then Edit and Apply to adopt the template."
echo 'The container, library files and appdata have not been changed.'
