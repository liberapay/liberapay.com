BEGIN;
    ALTER TABLE transfers ADD CONSTRAINT positive CHECK (amount > 0);
END;
