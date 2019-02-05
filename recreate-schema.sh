#!/bin/sh

# usage: DATABASE_URL=postgres://foo:bar@baz:5432/buz recreate-schema.sh

# Exit on errors and undefined variables
set -eu

alias psql='psql -v ON_ERROR_STOP=on'

if [ "${1-}" = "test" ]; then
    psql "$DATABASE_URL" <<EOF
DO \$$
BEGIN
    EXECUTE 'ALTER DATABASE '||current_database()||' SET synchronous_commit TO off';
END
\$$
EOF
fi

echo "=============================================================================="
echo "Applying sql/recreate-schema.sql ... "
echo
psql "$DATABASE_URL" < sql/recreate-schema.sql

echo "=============================================================================="
echo "Applying sql/app-conf-defaults.sql ... "
echo
psql "$DATABASE_URL" < sql/app-conf-defaults.sql

echo "=============================================================================="
echo "Looking for sql/branch.sql ..."
echo

if [ -f sql/branch.sql ]
then psql "$DATABASE_URL" < sql/branch.sql
else
    echo "None found. That's cool. You only need a sql/branch.sql file if you want to "
    echo "include schema changes with your pull request."
fi

if [ "${1-}" = "test" ]; then
    echo "=============================================================================="
    echo "Applying sql/app-conf-tests.sql ... "
    echo
    psql "$DATABASE_URL" < sql/app-conf-tests.sql
fi

echo
echo "=============================================================================="
