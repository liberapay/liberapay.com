BEGIN;

ALTER TABLE takes ADD COLUMN paid_in_advance currency_amount;
ALTER TABLE takes ADD CONSTRAINT paid_in_advance_currency_chk CHECK (paid_in_advance::currency = amount::currency);

CREATE INDEX takes_team_idx ON takes (team);
DROP VIEW current_takes;
CREATE VIEW current_takes AS
    SELECT *
      FROM ( SELECT DISTINCT ON (team, member) t.*
               FROM takes t
           ORDER BY team, member, mtime DESC
           ) AS x
     WHERE amount IS NOT NULL;

UPDATE takes AS take
   SET paid_in_advance = coalesce_currency_amount((
           SELECT sum(tr.amount, take.amount::currency)
             FROM transfers tr
            WHERE tr.tippee = take.member
              AND tr.team = take.team
              AND tr.context = 'take-in-advance'
              AND tr.status = 'succeeded'
       ), take.amount::currency) + coalesce_currency_amount((
           SELECT sum(pt.amount, take.amount::currency)
             FROM payin_transfers pt
            WHERE pt.recipient = take.member
              AND pt.team = take.team
              AND pt.context = 'team-donation'
              AND pt.status = 'succeeded'
       ), take.amount::currency) - coalesce_currency_amount((
           SELECT sum(tr.amount, take.amount::currency)
             FROM transfers tr
            WHERE tr.tippee = take.member
              AND tr.team = take.team
              AND tr.context = 'take'
              AND tr.status = 'succeeded'
              AND tr.virtual IS TRUE
       ), take.amount::currency)
  FROM current_takes ct
 WHERE take.id = ct.id;

END;
