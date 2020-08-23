UPDATE scheduled_payins
   SET execution_date = execution_date - interval '1 day'
 WHERE payin IS null
   AND execution_date > current_date
   AND last_notif_ts IS null
   AND automatic IS true;
