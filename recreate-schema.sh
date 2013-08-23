#!/bin/sh

set -e

# Make a database for Gittip.
#
#   usage: DATABASE_URL=postgres://foo:bar@baz:5234/buz recreate-schema.sh


# Parse DATABASE_URL
# ==================
# We will export PG* envvars based on the contents of DATABASE_URL. For 
# envvars, see http://www.postgresql.org/docs/current/static/libpq-envars.html
# I committed this but @pjz wrote it: https://gist.github.com/pjz/5855367.

if [ "$DATABASE_URL" = "" ]; then 
    echo "Please set DATABASE_URL, perhaps by sourcing default_tests.env or something.";
exit 1; fi

# remove the protocol
url=`echo $DATABASE_URL | sed -e s,postgres://,,g`

# extract the user (if any)
userpass="`echo $url | grep @ | cut -d@ -f1`"
pass=`echo $userpass | grep : | cut -d: -f2`
if [ -n "$pass" ]; then
    user=`echo $userpass | grep : | cut -d: -f1`
else
    user=$userpass
fi
 
# extract the host
hostport=`echo $url | sed -e s,$userpass@,,g | cut -d/ -f1`
port=`echo $hostport | grep : | cut -d: -f2`
if [ -n "$port" ]; then
    host=`echo $hostport | grep : | cut -d: -f1`
else
    host=$hostport
fi
 
# extract the path (if any)
path="`echo $url | grep / | cut -d/ -f2-`"

# export envvars for psql
export PGUSER=$user
export PGPASSWORD=$pass
export PGHOST=$host
export PGPORT=$port
export PGDATABASE=$path

echo 'PG environment variables:'
env | grep ^PG


echo "=============================================================================="

# I got the idea for dropping the schema as a way to clear out the db from
# http://www.postgresql.org/message-id/200408241254.19075.josh@agliodbs.com. On
# Heroku Postgres we don't have permission to drop and create the db as a 
# whole.

echo "Recreating public schema ... "
echo "DROP SCHEMA public CASCADE" | psql
echo "CREATE SCHEMA public" | psql


echo "=============================================================================="
echo "Applying schema.sql ..."
echo 

psql < enforce-utc.sql
psql < schema.sql


echo "=============================================================================="
echo "Looking for branch.sql ..."
echo 

if [ -f branch.sql ]
then psql < branch.sql
else echo "None found."
fi

echo 
echo "=============================================================================="
