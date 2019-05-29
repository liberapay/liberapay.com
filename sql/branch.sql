ALTER TYPE payin_status ADD VALUE IF NOT EXISTS 'awaiting_payer_action';
ALTER TABLE payins ADD COLUMN intent_id text;
