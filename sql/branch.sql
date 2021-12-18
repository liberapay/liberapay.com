ALTER TYPE route_status ADD VALUE IF NOT EXISTS 'expired';
UPDATE exchange_routes
   SET status = 'expired'
 WHERE id IN (
           SELECT DISTINCT ON (pi.route) pi.route
             FROM payins pi
            WHERE pi.error = 'Your card has expired. (code expired_card)'
         ORDER BY pi.route, pi.ctime DESC
       );
