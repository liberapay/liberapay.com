UPDATE scheduled_payins
   SET execution_date = '2020-02-14'
 WHERE execution_date < '2020-02-14'::date
   AND automatic IS TRUE;
