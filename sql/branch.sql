-- before deployment
BEGIN;

    ALTER TABLE cash_bundles
        ADD COLUMN withdrawal int REFERENCES exchanges,
        ALTER COLUMN owner DROP NOT NULL;

END;

-- after deployment
BEGIN;

    LOCK e2e_transfers IN EXCLUSIVE MODE;

    INSERT INTO cash_bundles
                (owner, origin, amount, ts)
         SELECT NULL, e2e.origin, e2e.amount
              , (SELECT e.timestamp FROM exchanges e WHERE e.id = e2e.origin)
           FROM e2e_transfers e2e
        ;

    DELETE FROM e2e_transfers;

END;

-- later (make sure the table is empty)
DROP TABLE e2e_transfers;
