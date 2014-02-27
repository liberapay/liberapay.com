BEGIN;
    ALTER TABLE participants ADD COLUMN paypal_masspay_fee_cap int;
    UPDATE participants SET paypal_masspay_fee_cap=20 WHERE paypal_email IS NOT NULL;
END;
