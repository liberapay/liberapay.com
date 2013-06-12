#!/bin/sh
echo "DROP SCHEMA public CASCADE" | psql "dbname=d14eguq4ovs8m host=ec2-54-225-91-60.compute-1.amazonaws.com user=vprkgneaqxaqvu password=jkaZ2shu3IBKGM0cHiXRnC8DJO port=5432 sslmode=require"
echo "CREATE SCHEMA public" | psql "dbname=d14eguq4ovs8m host=ec2-54-225-91-60.compute-1.amazonaws.com user=vprkgneaqxaqvu password=jkaZ2shu3IBKGM0cHiXRnC8DJO port=5432 sslmode=require"
psql "dbname=d14eguq4ovs8m host=ec2-54-225-91-60.compute-1.amazonaws.com user=vprkgneaqxaqvu password=jkaZ2shu3IBKGM0cHiXRnC8DJO port=5432 sslmode=require" < schema.sql
foreman run -e default_local.env ./env/bin/fake_data
