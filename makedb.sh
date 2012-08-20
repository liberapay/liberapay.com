#!/bin/sh

# Make a database for Gittip.
#
#   usage: makedb.sh {dbname} {owner}

DBNAME_DEFAULT=gittip
DBNAME=${1:-$DBNAME_DEFAULT}

OWNER_DEFAULT=$DBNAME
OWNER=${2:-$OWNER_DEFAULT}


echo "=============================================================================="
echo "Creating user ..."
echo 

createuser -s $OWNER

echo 
echo "=============================================================================="
echo "Dropping and creating db ..."
echo 

dropdb $DBNAME
createdb $DBNAME -O $OWNER

echo 
echo "=============================================================================="
echo "Applying schema.sql ..."
echo 

psql -U $OWNER $DBNAME < enforce-utc.sql
psql -U $OWNER $DBNAME < schema.sql

echo 
echo "=============================================================================="
