-- http://stackoverflow.com/questions/8092086/create-postgresql-role-user-if-it-doesnt-exist
-- http://www.postgresql.org/message-id/18380.994171549@sss.pgh.pa.us
DO
$body$
BEGIN
   IF NOT EXISTS (
      SELECT *
      FROM   pg_catalog.pg_database
      WHERE  datname = 'test3') THEN

      CREATE DATABASE test3 WITH OWNER=gittip;
   END IF;
END
$body$
