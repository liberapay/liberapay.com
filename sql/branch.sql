WITH pending_paypal_payins AS (
    SELECT pi.id
      FROM payins pi
      JOIN exchange_routes r ON r.id = pi.route
     WHERE r.network = 'paypal'
       AND pi.status = 'pending'
)
UPDATE payins
   SET status = 'awaiting_payer_action'
 WHERE id IN (SELECT * FROM pending_paypal_payins);
