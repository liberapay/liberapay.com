ALTER TABLE exchange_routes ADD COLUMN mandate text CHECK (mandate <> '');
ALTER TYPE exchange_status ADD VALUE IF NOT EXISTS 'pre-mandate';
