SELECT 'after deployment';

BEGIN;
    SET statement_timeout = 10000;
    LOCK TABLE currency_exchange_rates, participants, takes, tips, scheduled_payins IN EXCLUSIVE MODE;

    INSERT INTO currency_exchange_rates
         VALUES ('HRK', 'EUR', 1 / 7.53450)
              , ('EUR', 'HRK', 7.53450)
    ON CONFLICT (source_currency, target_currency) DO UPDATE
            SET rate = excluded.rate;

    UPDATE participants
       SET main_currency = 'EUR'
         , goal = convert(goal, 'EUR')
         , giving = convert(giving, 'EUR')
         , receiving = convert(receiving, 'EUR')
         , taking = convert(taking, 'EUR')
     WHERE main_currency = 'HRK';

    UPDATE participants
       SET accepted_currencies = (CASE
               WHEN accepted_currencies LIKE '%EUR%'
               THEN replace(replace(accepted_currencies, 'HRK', ''), ',,', '')
               ELSE replace(accepted_currencies, 'HRK', 'EUR')
           END)
     WHERE accepted_currencies LIKE '%HRK%';

    INSERT INTO tips
              ( ctime, tipper, tippee
              , amount, period, periodic_amount
              , paid_in_advance, is_funded, renewal_mode, visibility )
         SELECT ctime, tipper, tippee
              , convert(amount, 'EUR'), period, convert(periodic_amount, 'EUR')
              , convert(paid_in_advance, 'EUR'), is_funded, renewal_mode, visibility
           FROM current_tips
          WHERE (amount).currency = 'HRK';

    UPDATE scheduled_payins
       SET amount = convert(amount, 'EUR')
     WHERE (amount).currency = 'HRK';

    INSERT INTO takes
                (ctime, member, team, amount, actual_amount, recorder, paid_in_advance)
         SELECT ctime, member, team, convert(amount, 'EUR'), actual_amount, recorder, convert(paid_in_advance, 'EUR')
           FROM current_takes
          WHERE (amount).currency = 'HRK';
END;
