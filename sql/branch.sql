ALTER TABLE exchange_routes
    ADD COLUMN brand text,
    ADD COLUMN last4 text,
    ADD COLUMN fingerprint text,
    ADD COLUMN owner_name text,
    ADD COLUMN expiration_date date,
    ADD COLUMN mandate_reference text;
