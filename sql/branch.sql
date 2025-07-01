ALTER TYPE currency ADD VALUE IF NOT EXISTS 'XCG';
BEGIN;
UPDATE participants
   SET main_currency = 'XCG'
     , goal = ((goal).amount, 'XCG')::currency_amount
     , giving = ((giving).amount, 'XCG')::currency_amount
     , receiving = ((receiving).amount, 'XCG')::currency_amount
     , taking = ((taking).amount, 'XCG')::currency_amount
 WHERE main_currency = 'ANG';
UPDATE participants p
   SET accepted_currencies = replace(accepted_currencies, 'ANG', 'XCG')
 WHERE accepted_currencies LIKE '%ANG%';
INSERT INTO tips
          ( ctime, tipper, tippee
          , amount, period
          , periodic_amount
          , paid_in_advance
          , is_funded, renewal_mode, visibility )
     SELECT ctime, tipper, tippee
          , ((amount).amount, 'XCG')::currency_amount, period
          , ((periodic_amount).amount, 'XCG')::currency_amount
          , ((paid_in_advance).amount, 'XCG')::currency_amount
          , is_funded, renewal_mode, visibility
       FROM current_tips
      WHERE (amount).currency = 'ANG';
UPDATE scheduled_payins
   SET amount = ((amount).amount, 'XCG')::currency_amount
 WHERE (amount).currency = 'ANG';
INSERT INTO takes
            ( ctime, member, team, amount
            , actual_amount, recorder, paid_in_advance)
     SELECT ctime, member, team, ((amount).amount, 'XCG')::currency_amount
          , actual_amount, recorder, ((paid_in_advance).amount, 'XCG')::currency_amount
       FROM current_takes
      WHERE (amount).currency = 'ANG';
ROLLBACK;
