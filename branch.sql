BEGIN;
    DROP VIEW goal_summary;
    ALTER TABLE tips ADD COLUMN is_funded boolean;

    -- Needs to be recreated to include the new column
    DROP VIEW current_tips;
    CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;

    -- Allow updating is_funding via the current_tips view for convenience
    CREATE FUNCTION update_tip() RETURNS trigger AS $$
        BEGIN
            UPDATE tips
               SET is_funded = NEW.is_funded
             WHERE id = NEW.id;
            RETURN NULL;
        END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER update_current_tip INSTEAD OF UPDATE ON current_tips
        FOR EACH ROW EXECUTE PROCEDURE update_tip();

    \i fake_payday.sql
END;
