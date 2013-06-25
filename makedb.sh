#!/bin/sh

set -e

# Make a database for Gittip.
#
#   usage: makedb.sh

if [ "$DATABASE_URL" = "" ]; then 
    echo "You need to source a configuration environment, like default_tests.env or something.";
exit 1; fi


PGHOST=$DATABASE_URL
PGPORT=$DATABASE_URL
PGDATABASE=$DATABASE_URL
PGUSER=$DATABASE_URL
PGPASSWORD=$DATABASE_URL


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

echo "=============================================================================="
echo "Looking for branch.sql ..."
echo 

if [ -f branch.sql ]
then psql -U $OWNER $DBNAME < branch.sql
else echo "None found."
fi

echo 
echo "=============================================================================="
