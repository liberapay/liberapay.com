BEGIN;

    ALTER TABLE participants ADD COLUMN is_free_rider boolean DEFAULT NULL;

    UPDATE participants SET is_free_rider=FALSE WHERE (
        SELECT count(*)
          FROM current_tips
         WHERE tippee='Gittip' AND tipper=username AND amount > 0
    ) > 0;

END;
