BEGIN;
    \i sql/currencies.sql
END;

ALTER TABLE participants ADD COLUMN main_currency currency NOT NULL DEFAULT 'EUR';
ALTER TABLE participants ADD COLUMN accept_all_currencies boolean NOT NULL DEFAULT FALSE;

BEGIN;
    ALTER TABLE cash_bundles ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE debts ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE disputes ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE exchanges ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE exchanges ALTER COLUMN fee TYPE currency_amount USING (fee, 'EUR');
    ALTER TABLE exchanges ALTER COLUMN vat TYPE currency_amount USING (vat, 'EUR');
    ALTER TABLE invoices ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE transfers ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
END;

BEGIN;
    DROP VIEW current_tips;
    ALTER TABLE tips ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE tips ALTER COLUMN periodic_amount TYPE currency_amount USING (periodic_amount, 'EUR');
    CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
END;

BEGIN;

    CREATE TABLE wallets
    ( remote_id         text              NOT NULL UNIQUE
    , balance           currency_amount   NOT NULL CHECK (balance >= 0)
    , owner             bigint            NOT NULL REFERENCES participants
    , remote_owner_id   text              NOT NULL
    , is_current        boolean           DEFAULT TRUE
    );

    CREATE UNIQUE INDEX ON wallets (owner, (balance::currency), is_current);
    CREATE UNIQUE INDEX ON wallets (remote_owner_id, (balance::currency));

    INSERT INTO wallets
                (remote_id, balance, owner, remote_owner_id)
         SELECT p.mangopay_wallet_id
              , (p.balance, 'EUR')::currency_amount
              , p.id
              , p.mangopay_user_id
           FROM participants p
          WHERE p.mangopay_wallet_id IS NOT NULL;

    INSERT INTO wallets
                (remote_id, balance, owner, remote_owner_id, is_current)
         SELECT e.payload->'old_wallet_id'
              , ('0.00', 'EUR')::currency_amount
              , e.participant
              , e.payload->'old_user_id'
              , false
           FROM "events" e
          WHERE e.type = 'mangopay-account-change';

END;

CREATE FUNCTION EUR(numeric) RETURNS currency_amount AS $$
    BEGIN RETURN ($1, 'EUR'); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

BEGIN;
    DROP VIEW sponsors;
    ALTER TABLE participants DROP COLUMN mangopay_wallet_id;
    ALTER TABLE participants
        ALTER COLUMN goal DROP DEFAULT,
        ALTER COLUMN goal TYPE currency_amount USING EUR(goal),
        ALTER COLUMN goal SET DEFAULT NULL;
    ALTER TABLE participants
        ALTER COLUMN giving DROP DEFAULT,
        ALTER COLUMN giving TYPE currency_amount USING EUR(giving),
        ALTER COLUMN giving SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN receiving DROP DEFAULT,
        ALTER COLUMN receiving TYPE currency_amount USING EUR(receiving),
        ALTER COLUMN receiving SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN taking DROP DEFAULT,
        ALTER COLUMN taking TYPE currency_amount USING EUR(taking),
        ALTER COLUMN taking SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN leftover DROP DEFAULT,
        ALTER COLUMN leftover TYPE currency_amount USING EUR(leftover),
        ALTER COLUMN leftover SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN balance DROP DEFAULT,
        ALTER COLUMN balance TYPE currency_amount USING EUR(balance),
        ALTER COLUMN balance SET DEFAULT ('0.00', 'EUR');
    CREATE VIEW sponsors AS
        SELECT *
          FROM participants p
         WHERE status = 'active'
           AND kind = 'organization'
           AND giving > receiving
           AND giving >= 10
           AND hide_from_lists = 0
           AND profile_noindex = 0
        ;
END;

BEGIN;
    DROP VIEW current_takes;
    ALTER TABLE takes
        ALTER COLUMN amount DROP DEFAULT,
        ALTER COLUMN amount TYPE currency_amount USING EUR(amount),
        ALTER COLUMN amount SET DEFAULT NULL;
    ALTER TABLE takes
        ALTER COLUMN actual_amount DROP DEFAULT,
        ALTER COLUMN actual_amount TYPE currency_amount USING EUR(actual_amount),
        ALTER COLUMN actual_amount SET DEFAULT NULL;
    CREATE VIEW current_takes AS
        SELECT * FROM (
             SELECT DISTINCT ON (member, team) t.*
               FROM takes t
           ORDER BY member, team, mtime DESC
        ) AS anon WHERE amount IS NOT NULL;
END;

DROP FUNCTION EUR(numeric);

BEGIN;
    ALTER TABLE paydays
        ALTER COLUMN transfer_volume DROP DEFAULT,
        ALTER COLUMN transfer_volume TYPE currency_basket USING (transfer_volume, '0.00'),
        ALTER COLUMN transfer_volume SET DEFAULT ('0.00', '0.00');
    ALTER TABLE paydays
        ALTER COLUMN take_volume DROP DEFAULT,
        ALTER COLUMN take_volume TYPE currency_basket USING (take_volume, '0.00'),
        ALTER COLUMN take_volume SET DEFAULT ('0.00', '0.00');
    ALTER TABLE paydays
        ALTER COLUMN week_deposits DROP DEFAULT,
        ALTER COLUMN week_deposits TYPE currency_basket USING (week_deposits, '0.00'),
        ALTER COLUMN week_deposits SET DEFAULT ('0.00', '0.00');
    ALTER TABLE paydays
        ALTER COLUMN week_withdrawals DROP DEFAULT,
        ALTER COLUMN week_withdrawals TYPE currency_basket USING (week_withdrawals, '0.00'),
        ALTER COLUMN week_withdrawals SET DEFAULT ('0.00', '0.00');
    ALTER TABLE paydays
        ALTER COLUMN transfer_volume_refunded DROP DEFAULT,
        ALTER COLUMN transfer_volume_refunded TYPE currency_basket USING (transfer_volume_refunded, '0.00'),
        ALTER COLUMN transfer_volume_refunded SET DEFAULT ('0.00', '0.00');
    ALTER TABLE paydays
        ALTER COLUMN week_deposits_refunded DROP DEFAULT,
        ALTER COLUMN week_deposits_refunded TYPE currency_basket USING (week_deposits_refunded, '0.00'),
        ALTER COLUMN week_deposits_refunded SET DEFAULT ('0.00', '0.00');
    ALTER TABLE paydays
        ALTER COLUMN week_withdrawals_refunded DROP DEFAULT,
        ALTER COLUMN week_withdrawals_refunded TYPE currency_basket USING (week_withdrawals_refunded, '0.00'),
        ALTER COLUMN week_withdrawals_refunded SET DEFAULT ('0.00', '0.00');
END;

CREATE FUNCTION recompute_balance(bigint) RETURNS currency_amount AS $$
    UPDATE participants p
       SET balance = (
               SELECT sum(w.balance, p.main_currency)
                 FROM wallets w
                WHERE w.owner = p.id
           )
     WHERE id = $1
 RETURNING balance;
$$ LANGUAGE SQL STRICT;

DELETE FROM notifications WHERE event = 'low_balance';

BEGIN;
    ALTER TABLE balances_at ALTER COLUMN balance TYPE currency_basket USING (balance, '0.00');
    ALTER TABLE balances_at RENAME COLUMN balance TO balances;
END;
