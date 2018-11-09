UPDATE participants
   SET goal = (-1,main_currency)::currency_amount
 WHERE status = 'closed';
