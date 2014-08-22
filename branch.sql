BEGIN;
    ALTER TABLE tips ADD COLUMN is_funded boolean;
    \i fake_payday.sql
END;
