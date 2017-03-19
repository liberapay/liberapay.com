#!/bin/bash -eu

cd `dirname $0`
dest="$(dirname `pwd`)"
if [ "$(basename $dest)" != 'liberapay' ]; then echo "parent directory should be named 'liberapay'"; exit 1; fi
dest="$dest/backups"
mkdir -p $dest
dest="$dest/$(date -u -Iseconds).psql"
eb ssh liberapay-prod -c pg_dump >$dest
chmod 400 $dest
