ALTER TABLE paydays
    ADD COLUMN stage int,
    ALTER COLUMN stage SET DEFAULT 1;

INSERT INTO app_conf VALUES
    ('s3_payday_logs_bucket', '"archives.liberapay.org"'::jsonb);

INSERT INTO app_conf VALUES
    ('bot_github_username', '"liberapay-bot"'::jsonb),
    ('bot_github_token', '""'::jsonb),
    ('payday_repo', '"liberapay-bot/test"'::jsonb),
    ('payday_label', '"Payday"'::jsonb);

ALTER TABLE paydays ADD COLUMN public_log text;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/10' WHERE id = 1;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/12' WHERE id = 2;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/16' WHERE id = 3;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/19' WHERE id = 4;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/20' WHERE id = 5;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/24' WHERE id = 6;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/25' WHERE id = 7;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/27' WHERE id = 8;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/30' WHERE id = 9;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/31' WHERE id = 10;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/33' WHERE id = 11;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/35' WHERE id = 12;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/37' WHERE id = 13;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/38' WHERE id = 14;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/39' WHERE id = 15;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/40' WHERE id = 16;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/41' WHERE id = 17;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/44' WHERE id = 18;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/46' WHERE id = 19;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/47' WHERE id = 20;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/48' WHERE id = 21;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/51' WHERE id = 22;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/53' WHERE id = 23;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/55' WHERE id = 24;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/59' WHERE id = 25;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/60' WHERE id = 26;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/63' WHERE id = 27;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/64' WHERE id = 28;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/69' WHERE id = 29;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/71' WHERE id = 30;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/74' WHERE id = 31;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/75' WHERE id = 32;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/76' WHERE id = 33;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/77' WHERE id = 34;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/80' WHERE id = 35;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/81' WHERE id = 36;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/82' WHERE id = 37;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/83' WHERE id = 38;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/84' WHERE id = 39;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/86' WHERE id = 40;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/87' WHERE id = 41;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/88' WHERE id = 42;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/90' WHERE id = 43;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/92' WHERE id = 44;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/93' WHERE id = 45;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/94' WHERE id = 46;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/95' WHERE id = 47;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/101' WHERE id = 48;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/102' WHERE id = 49;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/103' WHERE id = 50;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/104' WHERE id = 51;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/105' WHERE id = 52;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/107' WHERE id = 53;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/109' WHERE id = 54;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/110' WHERE id = 55;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/112' WHERE id = 56;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/113' WHERE id = 57;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/115' WHERE id = 58;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/116' WHERE id = 59;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/117' WHERE id = 60;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/119' WHERE id = 61;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/124' WHERE id = 62;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/126' WHERE id = 63;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/129' WHERE id = 64;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/132' WHERE id = 65;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/133' WHERE id = 66;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/134' WHERE id = 67;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/135' WHERE id = 68;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/137' WHERE id = 69;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/139' WHERE id = 70;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/141' WHERE id = 71;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/143' WHERE id = 72;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/144' WHERE id = 73;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/147' WHERE id = 74;
UPDATE paydays SET public_log = 'https://github.com/liberapay/salon/issues/148' WHERE id = 75;
ALTER TABLE paydays ALTER COLUMN public_log SET NOT NULL;

ALTER TABLE paydays
    ALTER COLUMN ts_start DROP DEFAULT,
    ALTER COLUMN ts_start DROP NOT NULL;
