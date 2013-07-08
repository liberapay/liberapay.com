#!/bin/sh
# http://bytes.com/topic/postgresql/answers/577571-create-database-test-if-not-exists
ADMIN_ROLE=postgres
DB_OWNER=gittip
DBNAME=gittip

# Generate SQL to count our database if it exists
SQL_COUNT_DB="SELECT COUNT(1) FROM pg_catalog.pg_database WHERE datname = '$DBNAME';"

# Run the command and find out if our count is 0
DB_COUNT=$(psql --tuples-only --username $ADMIN_ROLE --command "$SQL_COUNT_DB" | grep 0)

# If there is no database, create it
if test "$DB_COUNT" != ""; then
  SQL_CREATE_DB="CREATE DATABASE $DBNAME WITH OWNER = $DB_OWNER;"
  psql --username $ADMIN_ROLE --command "$SQL_CREATE_DB"
fi

# Exit with success status
exit 0