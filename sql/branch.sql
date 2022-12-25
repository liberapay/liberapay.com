ALTER TYPE payin_status ADD VALUE IF NOT EXISTS 'awaiting_review';
ALTER TYPE payin_transfer_status ADD VALUE IF NOT EXISTS 'awaiting_review';
CREATE INDEX payins_awating_review ON payins (status) WHERE status = 'awaiting_review';
