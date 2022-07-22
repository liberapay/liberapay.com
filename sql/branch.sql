BEGIN;
    CREATE FUNCTION check_payin_transfer_update() RETURNS trigger AS $$
        BEGIN
            IF (OLD.status = 'succeeded' AND NEW.status = 'succeeded') THEN
                IF (NEW.amount <> OLD.amount) THEN
                    RAISE 'modifying the amount of an already successful transfer is not allowed';
                END IF;
            END IF;
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER check_payin_transfer_update BEFORE UPDATE ON payin_transfers
        FOR EACH ROW EXECUTE PROCEDURE check_payin_transfer_update();
END;

SELECT 'after deployment';

BEGIN;
    UPDATE payins SET remote_id = null WHERE remote_id = '';
    UPDATE payin_transfers SET remote_id = null WHERE remote_id = '';
END;
