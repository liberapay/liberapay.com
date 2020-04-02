ALTER TABLE payin_transfer_events
    ALTER COLUMN status TYPE payin_transfer_status USING status::text::payin_transfer_status;
