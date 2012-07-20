#!/bin/sh

# Make a database for Gittip.
#
#   usage: makedb.sh {dbname} {owner}

DBNAME_DEFAULT=gittip
DBNAME=${1:-$DBNAME_DEFAULT}

OWNER_DEFAULT=$DBNAME
OWNER=${1:-$OWNER_DEFAULT}

createuser -s $OWNER
dropdb $DBNAME
createdb $DBNAME -O $OWNER
psql $DBNAME < enforce-utc.sql
psql $DBNAME < schema.sql
