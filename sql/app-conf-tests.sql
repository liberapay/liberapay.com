CREATE OR REPLACE FUNCTION update_app_conf(k text, v jsonb) RETURNS void AS $$
    UPDATE app_conf SET value = v WHERE key = k;
$$ LANGUAGE sql;

DO $$
BEGIN
    PERFORM update_app_conf('check_email_domains', 'false'::jsonb);
    PERFORM update_app_conf('payin_methods', '{"*": true}'::jsonb);
END;
$$;

DROP FUNCTION update_app_conf(text, jsonb);

INSERT INTO currency_exchange_rates VALUES
    ('EUR', 'USD', 1.2),
    ('USD', 'EUR', 1 / 1.2),
    ('EUR', 'CHF', 1.1),
    ('CHF', 'EUR', 1 / 1.1),
    ('EUR', 'GBP', 0.9),
    ('GBP', 'EUR', 1 / 0.9),
    ('EUR', 'JPY', 125),
    ('JPY', 'EUR', 1 / 125.0),
    ('EUR', 'KRW', 1250),
    ('KRW', 'EUR', 1 / 1250.0);
