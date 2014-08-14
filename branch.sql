BEGIN;

    ALTER TABLE participants ADD COLUMN rides_free boolean DEFAULT NULL;

    UPDATE participants SET rides_free=FALSE WHERE (
        SELECT count(*)
          FROM current_tips
         WHERE tippee='Gittip' AND tipper=username AND amount > 0
    ) > 0;

END;
