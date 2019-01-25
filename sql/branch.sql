ALTER TABLE takes
    DROP CONSTRAINT not_negative,
    ADD CONSTRAINT amount_chk CHECK (amount IS NULL OR amount >= 0 OR (amount).amount = -1),
    ALTER COLUMN amount DROP DEFAULT;

SELECT 'after deployment';

UPDATE takes AS t
   SET amount = (-1,amount::currency)::currency_amount
     , mtime = current_timestamp
  FROM ( SELECT t2.id
           FROM current_takes t2
          WHERE t2.mtime = t2.ctime
       ) t2
 WHERE t.id = t2.id;
