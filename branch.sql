BEGIN;
    ALTER TABLE participants DROP COLUMN stripe_customer_id;
END;
