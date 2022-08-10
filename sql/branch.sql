BEGIN;
    UPDATE payins SET error = 'abandoned py payer' WHERE error = 'expired';
    UPDATE payin_events SET error = 'abandoned py payer' WHERE error = 'expired';
    UPDATE payin_transfers SET error = 'abandoned py payer' WHERE error = 'expired';
    UPDATE payin_transfer_events SET error = 'abandoned py payer' WHERE error = 'expired';
END;
