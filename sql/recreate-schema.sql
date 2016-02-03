SET client_min_messages = WARNING;
SET log_min_messages = WARNING;

-- We don't necessarily have permission to drop and create the db as a whole, so
-- we recreate the public schema instead.
-- http://www.postgresql.org/message-id/200408241254.19075.josh@agliodbs.com

DROP SCHEMA public CASCADE; CREATE SCHEMA public;

\i sql/schema.sql
