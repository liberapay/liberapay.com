CREATE OR REPLACE FUNCTION update_app_conf(k text, v jsonb) RETURNS void AS $$
    UPDATE app_conf SET value = v WHERE key = k;
$$ LANGUAGE sql;

DO $$
BEGIN
    PERFORM update_app_conf('check_db_every', '0'::jsonb);
    PERFORM update_app_conf('clean_up_counters_every', '0'::jsonb);
    PERFORM update_app_conf('dequeue_emails_every', '0'::jsonb);
    PERFORM update_app_conf('update_homepage_every', '0'::jsonb);
    PERFORM update_app_conf('send_newsletters_every', '0'::jsonb);
    PERFORM update_app_conf('refetch_elsewhere_data_every', '0'::jsonb);
    PERFORM update_app_conf('refetch_repos_every', '0'::jsonb);
END;
$$;

DROP FUNCTION update_app_conf(text, jsonb);

INSERT INTO currency_exchange_rates
     VALUES ('EUR', 'USD', 1.2)
          , ('USD', 'EUR', 1 / 1.2);
