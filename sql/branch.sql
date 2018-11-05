BEGIN;

ALTER TABLE tips ADD COLUMN renewal_mode int NOT NULL DEFAULT 1;
-- 0 means no renewal
-- 1 means manual renewal
-- 2 means automatic renewal (not implemented yet)

DROP VIEW current_tips;
CREATE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;

CREATE FUNCTION get_previous_tip(t tips) RETURNS tips AS $$
    SELECT old_t.*
      FROM tips old_t
     WHERE old_t.tipper = t.tipper
       AND old_t.tippee = t.tippee
       AND old_t.mtime < t.mtime
  ORDER BY old_t.mtime DESC
     LIMIT 1;
$$ LANGUAGE SQL STRICT STABLE;

DELETE FROM tips AS t
 WHERE t.periodic_amount = 0
   AND get_previous_tip(t) IS NULL;

DELETE FROM tips AS t
 WHERE t.amount = (get_previous_tip(t)).amount
   AND t.period = (get_previous_tip(t)).period
   AND t.periodic_amount = (get_previous_tip(t)).periodic_amount
   AND t.paid_in_advance = (get_previous_tip(t)).paid_in_advance;

UPDATE tips AS t
   SET amount = (get_previous_tip(t)).amount
     , periodic_amount = (get_previous_tip(t)).periodic_amount
     , period = (get_previous_tip(t)).period
     , paid_in_advance = (get_previous_tip(t)).paid_in_advance
     , renewal_mode = 0
 WHERE t.amount = 0;

DROP FUNCTION get_previous_tip(tips);

ALTER TABLE tips ADD CONSTRAINT tips_periodic_amount_check CHECK (periodic_amount > 0);

END;
