-- Create the necessary temporary tables and indexes

CREATE TEMPORARY TABLE temp_participants ON COMMIT DROP AS
    SELECT username
         , claimed_time
         , balance AS fake_balance
         , 0::numeric(35,2) AS giving
         , 0::numeric(35,2) AS pledging
         , 0::numeric(35,2) AS taking
         , 0::numeric(35,2) AS receiving
         , 0 as npatrons
         , goal
         , COALESCE(last_bill_result = '', false) AS credit_card_ok
      FROM participants
     WHERE is_suspicious IS NOT true;

CREATE UNIQUE INDEX ON temp_participants (username);

CREATE TEMPORARY TABLE temp_tips ON COMMIT DROP AS
    SELECT t.id, tipper, tippee, amount, (p2.claimed_time IS NOT NULL) AS claimed
      FROM current_tips t
      JOIN temp_participants p ON p.username = t.tipper
      JOIN temp_participants p2 ON p2.username = t.tippee
     WHERE t.amount > 0
       AND (p2.goal IS NULL or p2.goal >= 0)
  ORDER BY p2.claimed_time IS NULL, p.claimed_time ASC, t.ctime ASC;

CREATE INDEX ON temp_tips (tipper);
CREATE INDEX ON temp_tips (tippee);
ALTER TABLE temp_tips ADD COLUMN is_funded boolean NOT NULL DEFAULT false;

CREATE TEMPORARY TABLE temp_takes
( team text
, member text
, amount numeric(35,2)
) ON COMMIT DROP;


-- Create a trigger to process tips

CREATE OR REPLACE FUNCTION fake_tip() RETURNS trigger AS $$
    DECLARE
        tipper temp_participants;
    BEGIN
        tipper := (
            SELECT p.*::temp_participants
              FROM temp_participants p
             WHERE username = NEW.tipper
        );
        IF (NEW.amount > tipper.fake_balance AND NOT tipper.credit_card_ok) THEN
            RETURN NULL;
        END IF;
        IF (NEW.claimed) THEN
            UPDATE temp_participants
               SET fake_balance = (fake_balance - NEW.amount)
                 , giving = (giving + NEW.amount)
             WHERE username = NEW.tipper;
        ELSE
            UPDATE temp_participants
               SET fake_balance = (fake_balance - NEW.amount)
                 , pledging = (pledging + NEW.amount)
             WHERE username = NEW.tipper;
        END IF;
        UPDATE temp_participants
           SET fake_balance = (fake_balance + NEW.amount)
             , receiving = (receiving + NEW.amount)
             , npatrons = (npatrons + 1)
         WHERE username = NEW.tippee;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER fake_tip BEFORE UPDATE OF is_funded ON temp_tips
    FOR EACH ROW
    WHEN (NEW.is_funded IS true AND OLD.is_funded IS NOT true)
    EXECUTE PROCEDURE fake_tip();


-- Create a trigger to process takes

CREATE OR REPLACE FUNCTION fake_take() RETURNS trigger AS $$
    DECLARE
        actual_amount numeric(35,2);
        team_balance numeric(35,2);
    BEGIN
        team_balance := (
            SELECT fake_balance
              FROM temp_participants
             WHERE username = NEW.team
        );
        IF (team_balance <= 0) THEN RETURN NULL; END IF;
        actual_amount := NEW.amount;
        IF (team_balance < NEW.amount) THEN
            actual_amount := team_balance;
        END IF;
        UPDATE temp_participants
           SET fake_balance = (fake_balance - actual_amount)
         WHERE username = NEW.team;
        UPDATE temp_participants
           SET fake_balance = (fake_balance + actual_amount)
             , taking = (taking + actual_amount)
             , receiving = (receiving + actual_amount)
         WHERE username = NEW.member;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER fake_take AFTER INSERT ON temp_takes
    FOR EACH ROW EXECUTE PROCEDURE fake_take();


-- Create a function to settle whole tip graph

CREATE OR REPLACE FUNCTION settle_tip_graph() RETURNS void AS $$
    DECLARE
        count integer NOT NULL DEFAULT 0;
        i integer := 0;
    BEGIN
        LOOP
            i := i + 1;
            WITH updated_rows AS (
                 UPDATE temp_tips
                    SET is_funded = true
                  WHERE is_funded IS NOT true
              RETURNING *
            )
            SELECT COUNT(*) FROM updated_rows INTO count;
            IF (count = 0) THEN
                EXIT;
            END IF;
            IF (i > 50) THEN
                RAISE 'Reached the maximum number of iterations';
            END IF;
        END LOOP;
    END;
$$ LANGUAGE plpgsql;


-- Start fake payday

-- Step 1: tips
UPDATE temp_tips t
   SET is_funded = true
  FROM temp_participants p
 WHERE p.username = t.tipper
   AND p.credit_card_ok;

SELECT settle_tip_graph();

-- Step 2: team takes
INSERT INTO temp_takes
    SELECT team, member, amount
      FROM current_takes t
     WHERE t.amount > 0
       AND t.team IN (SELECT username FROM temp_participants)
       AND t.member IN (SELECT username FROM temp_participants)
  ORDER BY ctime DESC;

-- Step 3: tips again
SELECT settle_tip_graph();

-- Step 4: update the real tables
UPDATE tips t
   SET is_funded = tt.is_funded
  FROM temp_tips tt
 WHERE t.id = tt.id
   AND t.is_funded <> tt.is_funded;

UPDATE participants p
   SET giving = p2.giving
     , pledging = p2.pledging
     , taking = p2.taking
     , receiving = p2.receiving
     , npatrons = p2.npatrons
  FROM temp_participants p2
 WHERE p.username = p2.username
   AND ( p.giving <> p2.giving OR
         p.pledging <> p2.pledging OR
         p.taking <> p2.taking OR
         p.receiving <> p2.receiving OR
         p.npatrons <> p2.npatrons
       );

-- Clean up functions
DROP FUNCTION fake_take() CASCADE;
DROP FUNCTION fake_tip() CASCADE;
DROP FUNCTION settle_tip_graph() CASCADE;
