SELECT 'after deployment';

INSERT INTO currency_exchange_rates
     VALUES ('BGN', 'EUR', 1 / 1.95583)
          , ('EUR', 'BGN', 1.95583)
ON CONFLICT (source_currency, target_currency) DO UPDATE
        SET rate = excluded.rate;

BEGIN;
    LOCK TABLE participants IN EXCLUSIVE MODE;
    UPDATE participants
       SET main_currency = 'EUR'
         , goal = convert(goal, 'EUR')
         , giving = convert(giving, 'EUR')
         , receiving = convert(receiving, 'EUR')
         , taking = convert(taking, 'EUR')
     WHERE main_currency = 'BGN';
    UPDATE participants
       SET accepted_currencies = (CASE
               WHEN accepted_currencies LIKE '%EUR%'
               THEN btrim(replace(replace(accepted_currencies, 'BGN', ''), ',,', ','), ',')
               ELSE replace(accepted_currencies, 'BGN', 'EUR')
           END)
     WHERE accepted_currencies LIKE '%BGN%';
END;

BEGIN;
    LOCK TABLE tips IN EXCLUSIVE MODE;
    INSERT INTO tips
              ( ctime, tipper, tippee
              , amount, period, periodic_amount
              , paid_in_advance, is_funded, renewal_mode, visibility )
         SELECT ctime, tipper, tippee
              , convert(amount, 'EUR'), period, convert(periodic_amount, 'EUR')
              , convert(paid_in_advance, 'EUR'), is_funded, renewal_mode, visibility
           FROM current_tips
          WHERE (amount).currency = 'BGN';
END;

BEGIN;
    LOCK TABLE scheduled_payins IN EXCLUSIVE MODE;
    UPDATE scheduled_payins
       SET amount = convert(amount, 'EUR')
         , transfers = (CASE WHEN automatic THEN json_array(
               SELECT jsonb_set(
                   jsonb_set(
                       value::jsonb,
                       '{amount,amount}',
                       ('"' || (convert((value->'amount'->>'amount', 'BGN')::currency_amount, 'EUR')).amount::text || '"')::jsonb
                   ),
                   '{amount,currency}',
                   '"EUR"'::jsonb
               ) FROM json_array_elements(transfers)
           ) ELSE NULL END)
     WHERE (amount).currency = 'BGN'
       AND payin IS NULL;
END;

BEGIN;
    LOCK TABLE takes IN EXCLUSIVE MODE;
    INSERT INTO takes
                (ctime, member, team, amount, actual_amount, recorder, paid_in_advance)
         SELECT ctime, member, team, convert(amount, 'EUR'), actual_amount, recorder, convert(paid_in_advance, 'EUR')
           FROM current_takes
          WHERE (amount).currency = 'BGN';
END;
