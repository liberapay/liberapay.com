BEGIN;
    ALTER TABLE tips ADD COLUMN past_transfers_sum currency_amount;
    CREATE OR REPLACE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
END;
