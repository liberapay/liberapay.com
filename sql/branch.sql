BEGIN;
    ALTER TABLE exchange_routes DROP CONSTRAINT currency_chk;
    ALTER TABLE exchange_routes ADD COLUMN is_default boolean CHECK (NOT (is_default IS FALSE));
    CREATE UNIQUE INDEX exchange_routes_is_default_key ON exchange_routes (participant, is_default);
END;
