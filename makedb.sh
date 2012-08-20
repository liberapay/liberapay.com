#!/bin/sh

set -e

# Make a database for Gittip.
#
#   usage: makedb.sh {dbname} {owner}

DBNAME_DEFAULT=gittip
DBNAME=${1:-$DBNAME_DEFAULT}

OWNER_DEFAULT=$DBNAME
OWNER=${2:-$OWNER_DEFAULT}


echo "=============================================================================="
printf "Creating user ... "

createuser -s $OWNER && echo "done" || :

echo "=============================================================================="
printf "Dropping db ... "

dropdb $DBNAME && echo "done" || :

echo "=============================================================================="
printf "Creating db ... "

createdb $DBNAME -O $OWNER && echo "done"

echo "=============================================================================="
echo "Applying schema.sql ..."
echo 

psql -U $OWNER $DBNAME < enforce-utc.sql
psql -U $OWNER $DBNAME < schema.sql

echo 
echo "=============================================================================="
