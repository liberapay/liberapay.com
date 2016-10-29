ALTER TABLE transfers
    DROP CONSTRAINT team_chk,
    ADD CONSTRAINT team_chk CHECK (NOT (context='take' AND team IS NULL));
