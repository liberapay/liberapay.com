UPDATE exchange_routes
   SET currency = 'EUR'
 WHERE network = 'stripe-sdd'
   AND currency IS NULL;
