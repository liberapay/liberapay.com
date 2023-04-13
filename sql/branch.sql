CREATE OR REPLACE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
    SELECT coalesce((
        SELECT sum(DISTINCT array_position(
                                enum_range(NULL::payment_providers),
                                a.provider::payment_providers
                            ))
          FROM payment_accounts a
         WHERE ( a.participant = $1 OR
                 a.participant IN (
                     SELECT t.member
                       FROM current_takes t
                      WHERE t.team = $1
                        AND t.amount <> 0
                 )
               )
           AND a.is_current IS TRUE
           AND a.verified IS TRUE
           AND coalesce(a.charges_enabled, true)
    ), 0);
$$ LANGUAGE SQL STRICT;

UPDATE participants
   SET payment_providers = compute_payment_providers(id)
 WHERE status <> 'stub'
   AND payment_providers = 0
   AND email IS NOT NULL
   AND join_time >= '2022-12-06'
   AND compute_payment_providers(id) <> 0;
