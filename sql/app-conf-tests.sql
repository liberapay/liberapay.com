CREATE OR REPLACE FUNCTION update_app_conf(k text, v jsonb) RETURNS void AS $$
    UPDATE app_conf SET value = v WHERE key = k;
$$ LANGUAGE sql;

DO $$
BEGIN
    PERFORM update_app_conf('check_db_every', '0'::jsonb);
    PERFORM update_app_conf('update_homepage_every', '0'::jsonb);
END;
$$;

DROP FUNCTION update_app_conf(text, jsonb);
