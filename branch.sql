BEGIN;

    ALTER TABLE participants ADD COLUMN takes numeric(35,2) NOT NULL DEFAULT 0;

    CREATE TEMPORARY TABLE temp_teams AS
        SELECT username, receiving
          FROM participants
         WHERE "number" = 'plural';

    CREATE TEMPORARY TABLE temp_takes
    ( team text
    , member text
    , amount numeric(35,2)
    );

    CREATE FUNCTION process_take() RETURNS trigger AS $$
        DECLARE
            actual_amount numeric(35,2);
            team_balance numeric(35,2);
        BEGIN
            team_balance := (
                SELECT receiving
                  FROM temp_teams
                 WHERE username = NEW.team
            );
            actual_amount := NEW.amount;
            IF (team_balance < NEW.amount) THEN
                actual_amount := team_balance;
            END IF;
            UPDATE participants
               SET takes = (takes + actual_amount)
                 , receiving = (receiving + actual_amount)
             WHERE username = NEW.member;
            UPDATE temp_teams
               SET receiving = (receiving - actual_amount)
             WHERE username = NEW.team;
            RETURN NULL;
        END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER process_take AFTER INSERT ON temp_takes
        FOR EACH ROW EXECUTE PROCEDURE process_take();

    INSERT INTO temp_takes
        SELECT team, member, amount
          FROM current_takes t
         WHERE t.amount > 0
      ORDER BY ctime DESC;

END;
