
-- Enforce UTC
-- ===========
-- The production db is already in UTC (presumably per postgresql.conf). We
-- need local dev dbs to also use UTC, but we don't want to make users edit
-- postgresql.conf themselves, nor do we want to clutter schema.sql with this,
-- nor do we want to do it in the application layer per-session. So it's here
-- instead, and is applied in recreate-schema.sh. From the docs on ALTER
-- DATABASE:
--
--      The remaining forms change the session default for a run-time
--      configuration variable for a PostgreSQL database. Whenever a new
--      session is subsequently started in that database, the specified value
--      becomes the session default value. The database-specific default
--      overrides whatever setting is present in postgresql.conf or has been
--      received from the postgres command line."
--
--      http://www.postgresql.org/docs/current/static/sql-alterdatabase.html
--
-- See also:
--
--      "Time Zones"
--      http://www.postgresql.org/docs/current/interactive/datatype-datetime.html#DATATYPE-TIMEZONES
--
--      "Setting Parameters"
--      http://www.postgresql.org/docs/current/static/config-setting.html
--
--      "How can I execute ALTER DATABASE $current_database in PostgreSQL"
--      http://stackoverflow.com/q/10212707/253309

DO $$
BEGIN
EXECUTE 'ALTER DATABASE "' || current_database() || '" SET timezone TO ''UTC'' ';
END; $$;
