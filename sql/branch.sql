CREATE TYPE currency AS ENUM ('EUR', 'USD');
ALTER TABLE participants ADD COLUMN main_currency currency NOT NULL DEFAULT 'EUR';
ALTER TABLE participants ADD COLUMN accept_all_currencies boolean NOT NULL DEFAULT FALSE;
