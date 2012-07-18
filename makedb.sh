#!/bin/sh
createuser -s gittip
dropdb gittip
createdb gittip -O gittip
psql gittip < schema.sql
