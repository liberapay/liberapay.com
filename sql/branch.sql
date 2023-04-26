CREATE OR REPLACE FUNCTION update_profile_visibility() RETURNS trigger AS $$
    BEGIN
        IF (OLD.marked_as IS NULL AND NEW.marked_as IS NULL) THEN
            RETURN NEW;
        END IF;
        IF (NEW.marked_as = 'trusted') THEN
            NEW.is_suspended = false;
        ELSIF (NEW.marked_as IN ('fraud', 'spam')) THEN
            NEW.is_suspended = true;
        ELSE
            NEW.is_suspended = null;
        END IF;
        IF (NEW.marked_as = 'unsettling') THEN
            NEW.is_unsettling = NEW.is_unsettling | 2;
        ELSE
            NEW.is_unsettling = NEW.is_unsettling & 2147483645;
        END IF;
        IF (NEW.marked_as IN ('okay', 'trusted')) THEN
            NEW.profile_noindex = NEW.profile_noindex & 2147483645;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSE
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists | 2;
            NEW.hide_from_search = NEW.hide_from_search | 2;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;

UPDATE participants
   SET marked_as = marked_as
 WHERE marked_as IS NULL AND ( is_suspended OR hide_from_lists & 2 = 2 )
    OR marked_as = 'unsettling';

UPDATE payin_transfers SET error = '' WHERE error = 'None (code None)';
UPDATE payin_transfer_events SET error = '' WHERE error = 'None (code None)';
