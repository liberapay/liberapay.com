#!/bin/sh

# usage: DATABASE_URL=postgres://foo:bar@baz:5234/buz recreate-schema.sh

# Exit if any subcommands or pipeline returns a non-zero status.
set -e

echo "=============================================================================="

# We don't necessarily have permission to drop and create the db as a whole, so
# we recreate the public schema instead.
# http://www.postgresql.org/message-id/200408241254.19075.josh@agliodbs.com

echo "Recreating public schema ... "
psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"


echo "=============================================================================="
echo "Applying sql/schema.sql ..."
echo

if [ "$1" = "test" ]; then
    psql $DATABASE_URL <<EOF
DO \$$
BEGIN
    EXECUTE 'ALTER DATABASE '||current_database()||' SET synchronous_commit TO off';
END
\$$
EOF
fi
psql $DATABASE_URL < sql/schema.sql


echo "=============================================================================="
echo "Looking for sql/branch.sql ..."
echo

if [ -f sql/branch.sql ]
then psql $DATABASE_URL < sql/branch.sql
else
    echo "None found. That's cool. You only need a sql/branch.sql file if you want to "
    echo "include schema changes with your pull request."
fi

echo
echo "=============================================================================="
