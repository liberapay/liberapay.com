#!/bin/bash -eu

cd "$(dirname "$0")"
dest_dir="$(dirname "$(pwd)")"
if [ "$(basename "$dest_dir")" != 'liberapay' ]; then echo "parent directory should be named 'liberapay'"; exit 1; fi
dest_dir="$dest_dir/backups"
mkdir -p "$dest_dir"
dest="$dest_dir/$(date -u -Iseconds).psql"
eb ssh liberapay -c "pg_dump -Fc" > "$dest"
chmod 400 "$dest"
ls -lh "$dest_dir" | tail -10
