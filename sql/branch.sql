BEGIN;

ALTER TABLE participants
    ADD COLUMN is_controversial boolean,
    ADD COLUMN is_spam boolean;

CREATE FUNCTION update_profile_visibility() RETURNS trigger AS $$
    BEGIN
        IF (NEW.is_controversial OR NEW.is_spam OR NEW.is_suspended) THEN
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists | 2;
            NEW.hide_from_search = NEW.hide_from_search | 2;
        ELSIF (NEW.is_controversial IS false) THEN
            NEW.profile_noindex = NEW.profile_noindex & 2147483645;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSE
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_profile_visibility
    BEFORE INSERT OR UPDATE ON participants
    FOR EACH ROW EXECUTE PROCEDURE update_profile_visibility();

END;
