BEGIN;

CREATE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
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
                 )
               )
           AND a.is_current IS TRUE
           AND a.verified IS TRUE
           AND coalesce(a.charges_enabled, true)
    ), 0);
$$ LANGUAGE SQL STRICT;

CREATE FUNCTION update_team_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = compute_payment_providers(rec.team)
         WHERE id = rec.team;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_team_payment_providers
    AFTER INSERT OR DELETE ON takes
    FOR EACH ROW EXECUTE PROCEDURE update_team_payment_providers();

CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = compute_payment_providers(rec.participant)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

END;

SELECT 'after deployment';

UPDATE participants
   SET payment_providers = compute_payment_providers(id)
 WHERE kind = 'group'
   AND payment_providers <> compute_payment_providers(id);
