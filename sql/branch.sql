ALTER TABLE participants ALTER COLUMN email_notif_bits SET DEFAULT 2147483646;
UPDATE notifications SET web = false WHERE event = 'income~v2';
