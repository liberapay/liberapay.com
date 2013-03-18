-- http://stackoverflow.com/questions/8092086/create-postgresql-role-user-if-it-doesnt-exist
DO
$body$
BEGIN
   IF NOT EXISTS (
      SELECT *
      FROM   pg_catalog.pg_user
      WHERE  usename = 'gittip') THEN

      CREATE ROLE gittip LOGIN PASSWORD 'gittip' SUPERUSER;
   END IF;
END
$body$
