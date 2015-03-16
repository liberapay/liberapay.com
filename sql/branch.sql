BEGIN;

    ALTER TABLE elsewhere ADD COLUMN connect_token text,
                          ADD COLUMN connect_expires timestamptz;

    DROP TYPE elsewhere_with_participant CASCADE;
    \i sql/elsewhere_with_participant.sql

END;
