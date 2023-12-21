ALTER TABLE recipient_settings
    ALTER COLUMN patron_visibilities DROP NOT NULL,
    ADD COLUMN patron_countries text CHECK (patron_countries <> '');
