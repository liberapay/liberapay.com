BEGIN;
    ALTER TABLE tips ADD COLUMN paid_in_advance currency_amount;

    DROP VIEW current_tips;
    CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
    DROP FUNCTION update_tip();
END;
