ALTER TABLE exchange_routes ADD COLUMN mandate text CHECK (mandate <> '');
ALTER TYPE exchange_status ADD VALUE IF NOT EXISTS 'pre-mandate';

INSERT INTO app_conf (key, value) VALUES
    ('show_sandbox_warning', 'true'::jsonb);
