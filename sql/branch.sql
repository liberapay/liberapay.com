ALTER TABLE exchanges ADD COLUMN remote_id text;

SELECT 'after deployment';

ALTER TABLE exchanges
    ADD CONSTRAINT remote_id_null_chk CHECK ((status::text LIKE 'pre%') = (remote_id IS NULL)),
    ADD CONSTRAINT remote_id_empty_chk CHECK (NOT (status <> 'failed' AND remote_id = ''));
