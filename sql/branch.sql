CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = coalesce((
                   SELECT sum(DISTINCT array_position(
                                           enum_range(NULL::payment_providers),
                                           a.provider::payment_providers
                                       ))
                     FROM payment_accounts a
                    WHERE ( a.participant = rec.participant OR
                            a.participant IN (
                                SELECT t.member
                                  FROM current_takes t
                                 WHERE t.team = rec.participant
                            )
                          )
                      AND a.is_current IS TRUE
                      AND a.verified IS TRUE
                      AND coalesce(a.charges_enabled, true)
               ), 0)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

UPDATE participants AS p
   SET payment_providers = coalesce((
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
                    )
                  )
              AND a.is_current IS TRUE
              AND a.verified IS TRUE
              AND coalesce(a.charges_enabled, true)
       ), 0)
 WHERE EXISTS (
           SELECT a.id
             FROM payment_accounts a
            WHERE a.participant = p.id
              AND a.charges_enabled IS false
       );
