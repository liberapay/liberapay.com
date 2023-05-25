CREATE OR REPLACE FUNCTION update_payment_accounts() RETURNS trigger AS $$
    BEGIN
        UPDATE payment_accounts
           SET verified = coalesce(NEW.verified, false)
         WHERE participant = NEW.participant
           AND lower(id) = lower(NEW.address);
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

UPDATE payment_accounts AS a
   SET verified = true
 WHERE lower(id) <> id
   AND NOT verified
   AND EXISTS (
           SELECT 1
             FROM emails e
            WHERE e.participant = a.participant
              AND lower(e.address) = lower(a.id)
              AND e.verified
       );
