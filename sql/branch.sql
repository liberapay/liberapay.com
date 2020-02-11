UPDATE scheduled_payins
   SET execution_date = '2020-02-14'
 WHERE execution_date < '2020-02-14'::date
   AND automatic IS TRUE
   AND payin IS NULL;

UPDATE scheduled_payins
   SET execution_date = (SELECT pi.ctime::date FROM payins pi WHERE pi.id = payin)
 WHERE execution_date < '2020-02-14'::date
   AND automatic IS TRUE
   AND payin IS NOT NULL;
