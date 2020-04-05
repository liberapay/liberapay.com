CREATE FUNCTION update_pending_notifs() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET pending_notifs = (
                   SELECT count(*)
                     FROM notifications
                    WHERE participant = rec.participant
                      AND web
                      AND is_new
               )
         WHERE id = rec.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_pending_notifs
    AFTER INSERT OR UPDATE OF is_new, web OR DELETE ON notifications
    FOR EACH ROW EXECUTE PROCEDURE update_pending_notifs();
