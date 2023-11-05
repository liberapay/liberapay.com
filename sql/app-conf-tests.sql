CREATE OR REPLACE FUNCTION update_app_conf(k text, v jsonb) RETURNS void AS $$
    UPDATE app_conf SET value = v WHERE key = k;
$$ LANGUAGE sql;

DO $$
BEGIN
    PERFORM update_app_conf('check_avatar_urls', 'false'::jsonb);
    PERFORM update_app_conf('check_email_domains', 'false'::jsonb);
    PERFORM update_app_conf('payin_methods', '{"*": true}'::jsonb);
    PERFORM update_app_conf('s3_endpoint', '"https://tests.liberapay.org"'::jsonb);
    PERFORM update_app_conf('s3_secret_key', '"fake"'::jsonb);
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
    ('KRW', 'EUR', 1 / 1250.0),

    ('EUR', 'BGN', '1.9558'),
    ('BGN', 'EUR', '0.51129972389814909500'),
    ('EUR', 'CZK', '25.718'),
    ('CZK', 'EUR', '0.03888327241620654794'),
    ('EUR', 'DKK', '7.4659'),
    ('DKK', 'EUR', '0.13394232443509824669'),
    ('EUR', 'HUF', '323.33'),
    ('HUF', 'EUR', '0.00309281538984937989'),
    ('EUR', 'PLN', '4.2934'),
    ('PLN', 'EUR', '0.23291563795593236130'),
    ('EUR', 'RON', '4.7615'),
    ('RON', 'EUR', '0.21001785151737897721'),
    ('EUR', 'SEK', '10.7973'),
    ('SEK', 'EUR', '0.09261574652922489882'),
    ('EUR', 'ISK', '137.20'),
    ('ISK', 'EUR', '0.00728862973760932945'),
    ('EUR', 'NOK', '9.8068'),
    ('NOK', 'EUR', '0.10197006158991720031'),
    ('EUR', 'HRK', '7.53450'),
    ('HRK', 'EUR', '0.13272280841462605349'),
    ('EUR', 'RUB', '73.0572'),
    ('RUB', 'EUR', '0.01368790481978504514'),
    ('EUR', 'TRY', '6.9725'),
    ('TRY', 'EUR', '0.14342058085335245608'),
    ('EUR', 'AUD', '1.6046'),
    ('AUD', 'EUR', '0.62320827620590801446'),
    ('EUR', 'BRL', '4.4368'),
    ('BRL', 'EUR', '0.22538766678687342229'),
    ('EUR', 'CAD', '1.5093'),
    ('CAD', 'EUR', '0.66255880209368581462'),
    ('EUR', 'CNY', '7.6374'),
    ('CNY', 'EUR', '0.13093461125513918349'),
    ('EUR', 'HKD', '8.7844'),
    ('HKD', 'EUR', '0.11383816766085333090'),
    ('EUR', 'IDR', '16062.37'),
    ('IDR', 'EUR', '0.000062257313210939606048'),
    ('EUR', 'ILS', '3.9973'),
    ('ILS', 'EUR', '0.25016886398318865234'),
    ('EUR', 'INR', '78.3435'),
    ('INR', 'EUR', '0.01276430080351273558'),
    ('EUR', 'MXN', '21.4412'),
    ('MXN', 'EUR', '0.04663918064287446598'),
    ('EUR', 'MYR', '4.6480'),
    ('MYR', 'EUR', '0.21514629948364888124'),
    ('EUR', 'NZD', '1.7015'),
    ('NZD', 'EUR', '0.58771672054069938290'),
    ('EUR', 'PHP', '58.477'),
    ('PHP', 'EUR', '0.01710074046206200728'),
    ('EUR', 'SGD', '1.5266'),
    ('SGD', 'EUR', '0.65505043888379405214'),
    ('EUR', 'THB', '35.577'),
    ('THB', 'EUR', '0.02810804733395171037'),
    ('EUR', 'ZAR', '16.0432'),
    ('ZAR', 'EUR', '0.06233170439812506233')
    ON CONFLICT (source_currency, target_currency) DO UPDATE SET rate = excluded.rate;
