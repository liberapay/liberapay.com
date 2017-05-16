ALTER TABLE elsewhere
    ALTER COLUMN user_id DROP NOT NULL,
    ADD CONSTRAINT user_id_chk CHECK (user_id IS NOT NULL OR domain <> '' AND user_name IS NOT NULL);
