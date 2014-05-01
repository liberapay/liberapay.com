BEGIN;

    ALTER TABLE transfers ADD COLUMN as_team_member boolean NOT NULL DEFAULT false;

    UPDATE transfers
       SET as_team_member = true
     WHERE amount <= (
               SELECT amount
                 FROM takes
                WHERE takes.team = transfers.tipper
                  AND takes.member = transfers.tippee
                  AND takes.ctime < transfers.timestamp
             ORDER BY takes.ctime DESC
                LIMIT 1
           )
       AND amount != (
               SELECT amount
                 FROM tips
                WHERE tips.ctime < transfers.timestamp
             ORDER BY tips.ctime DESC
                LIMIT 1
           );

END;
