#!/usr/bin/env bash

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

# echo envvars for psql
echo PGUSER=$user
echo PGPASSWORD=$pass
echo PGHOST=$host
echo PGPORT=$port
echo PGDATABASE=$path
