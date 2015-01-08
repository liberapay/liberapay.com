BEGIN;

DO $$
DECLARE
    payday record;
    new_ncharges int;
    new_charge_volume decimal(35,2);
    new_charge_fees_volume decimal(35,2);
BEGIN
    FOR payday IN SELECT * FROM paydays LOOP
        CREATE TEMP TABLE our_charges AS
            SELECT *
              FROM exchanges
             WHERE "timestamp" >= payday.ts_start
               AND "timestamp" < payday.ts_end
               AND amount > 0
               AND (status IS NULL OR status <> 'failed');
        new_ncharges := (SELECT count(*) FROM our_charges);
        new_charge_volume := (SELECT COALESCE(sum(amount + fee), 0) FROM our_charges);
        new_charge_fees_volume := (SELECT COALESCE(sum(fee), 0) FROM our_charges);
        UPDATE paydays
           SET ncharges = new_ncharges
             , charge_volume = new_charge_volume
             , charge_fees_volume = new_charge_fees_volume
         WHERE id = payday.id
           AND (ncharges <> new_ncharges
                OR charge_volume <> new_charge_volume
                OR charge_fees_volume <> new_charge_fees_volume);
        DROP TABLE our_charges;
    END LOOP;
END
$$;

END;
