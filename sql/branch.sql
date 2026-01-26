ALTER TABLE payin_transfers ADD CONSTRAINT reversed_destination_amount_chk CHECK (reversed_destination_amount > 0);
ALTER TABLE payin_transfer_reversals ADD CONSTRAINT destination_amount_chk CHECK (destination_amount > 0);
