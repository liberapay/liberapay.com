CREATE OR REPLACE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
    SELECT CASE WHEN p.email IS NULL AND p.kind <> 'group' AND p.join_time >= '2022-12-06' THEN 0
           ELSE coalesce((
               SELECT sum(DISTINCT array_position(
                                       enum_range(NULL::payment_providers),
                                       a.provider::payment_providers
                                   ))
                 FROM payment_accounts a
                WHERE ( a.participant = p.id OR
                        a.participant IN (
                            SELECT t.member
                              FROM current_takes t
                             WHERE t.team = p.id
                               AND t.amount <> 0
                        )
                      )
                  AND a.is_current IS TRUE
                  AND a.verified IS TRUE
                  AND coalesce(a.charges_enabled, true)
           ), 0) END
      FROM participants p
     WHERE p.id = $1;
$$ LANGUAGE SQL STRICT;
