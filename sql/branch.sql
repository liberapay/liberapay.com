CREATE OR REPLACE FUNCTION update_payment_accounts() RETURNS trigger AS $$
    BEGIN
        UPDATE payment_accounts
           SET verified = coalesce(NEW.verified, false)
         WHERE id = NEW.address
           AND participant = NEW.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_payment_accounts
    AFTER INSERT OR UPDATE ON emails
    FOR EACH ROW EXECUTE PROCEDURE update_payment_accounts();

UPDATE payment_accounts AS a
   SET verified = true
 WHERE verified IS NOT true
   AND ( SELECT e.verified
           FROM emails e
          WHERE e.address = a.id
            AND e.participant = a.participant
       ) IS true;
