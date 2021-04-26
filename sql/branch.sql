BEGIN;

CREATE TYPE account_mark AS ENUM (
    'trusted', 'okay', 'unsettling',
    'controversial', 'irrelevant', 'misleading',
    'spam', 'fraud'
);

ALTER TABLE participants
    ADD COLUMN marked_as account_mark,
    ADD COLUMN is_unsettling int NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION update_profile_visibility() RETURNS trigger AS $$
    BEGIN
        IF (NEW.marked_as IS NULL) THEN
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
        ELSIF (NEW.marked_as = 'unsettling') THEN
            NEW.profile_noindex = NEW.profile_noindex | 2;
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

END;

SELECT 'after deployment';

BEGIN;

UPDATE participants
   SET marked_as = 'spam'
 WHERE is_spam
   AND marked_as IS NULL;
UPDATE participants
   SET marked_as = 'controversial'
 WHERE is_controversial
   AND marked_as IS NULL;
UPDATE participants
   SET marked_as = 'trusted'
 WHERE is_suspended IS FALSE
   AND marked_as IS NULL;

ALTER TABLE participants
    DROP COLUMN is_controversial,
    DROP COLUMN is_spam;

-- Repair some of the damage caused by #1993
WITH _events AS (
    SELECT DISTINCT ON (e.participant)
           e.participant
         , ( CASE WHEN e.payload->>'profile_noindex' = 'true'
                  THEN p.profile_noindex | 2
                  ELSE p.profile_noindex & 2147483645
             END
           ) AS profile_noindex
         , ( CASE WHEN e.payload->>'hide_from_lists' = 'true'
                  THEN p.hide_from_lists | 2
                  ELSE p.hide_from_lists & 2147483645
             END
           ) AS hide_from_lists
         , ( CASE WHEN e.payload->>'hide_from_search' = 'true'
                  THEN p.hide_from_search | 2
                  ELSE p.hide_from_search & 2147483645
             END
           ) AS hide_from_search
      FROM events e
      JOIN participants p ON p.id = e.participant
     WHERE e.type = 'visibility_override'
  ORDER BY e.participant, e.ts DESC
)
UPDATE participants p
   SET profile_noindex = e.profile_noindex
     , hide_from_lists = e.hide_from_lists
     , hide_from_search = e.hide_from_search
  FROM _events e
 WHERE e.participant = p.id
   AND p.marked_as IS NULL
   AND ( p.profile_noindex <> e.profile_noindex OR
         p.hide_from_lists <> e.hide_from_lists OR
         p.hide_from_search <> e.hide_from_search
       );

UPDATE participants
   SET marked_as = 'okay'
 WHERE profile_noindex < 2
   AND marked_as IS NULL;

END;
