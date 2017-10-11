BEGIN;

ALTER TABLE takes
    ADD COLUMN actual_amount numeric(35,2),
    ADD COLUMN ntippers int;

ALTER TABLE participants
    ADD COLUMN nteampatrons int NOT NULL DEFAULT 0,
    ADD COLUMN leftover numeric(35,2) NOT NULL DEFAULT 0 CHECK (leftover >= 0),
    ADD CONSTRAINT receiving_chk CHECK (receiving >= 0),
    ADD CONSTRAINT taking_chk CHECK (taking >= 0);

CREATE OR REPLACE VIEW current_takes AS
    SELECT * FROM (
         SELECT DISTINCT ON (member, team) t.*
           FROM takes t
       ORDER BY member, team, mtime DESC
    ) AS anon WHERE amount IS NOT NULL;

END;
