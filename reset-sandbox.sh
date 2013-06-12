#!/bin/sh

# I got the idea for dropping the schema as a way to clear out the db from
# http://www.postgresql.org/message-id/200408241254.19075.josh@agliodbs.com. I
# don't have permission to drop and create the db as a whole on Heroku
# Postgres.

echo "DROP SCHEMA public CASCADE" | psql "dbname=d14eguq4ovs8m host=ec2-54-225-91-60.compute-1.amazonaws.com user=vprkgneaqxaqvu password=jkaZ2shu3IBKGM0cHiXRnC8DJO port=5432 sslmode=require"
echo "CREATE SCHEMA public" | psql "dbname=d14eguq4ovs8m host=ec2-54-225-91-60.compute-1.amazonaws.com user=vprkgneaqxaqvu password=jkaZ2shu3IBKGM0cHiXRnC8DJO port=5432 sslmode=require"
psql "dbname=d14eguq4ovs8m host=ec2-54-225-91-60.compute-1.amazonaws.com user=vprkgneaqxaqvu password=jkaZ2shu3IBKGM0cHiXRnC8DJO port=5432 sslmode=require" < schema.sql
foreman run -e default_local.env ./env/bin/fake_data
