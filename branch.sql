BEGIN;
    DELETE FROM transfers WHERE amount = 0 AND context = 'take-over';
    ALTER TABLE transfers ADD CONSTRAINT positive CHECK (amount > 0) NOT VALID;
END;
