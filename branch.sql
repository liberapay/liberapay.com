BEGIN;
    UPDATE participants p
       SET number = 'plural'::participant_number
     WHERE claimed_time IS NULL
       AND p.username in (
               SELECT participant
                 FROM elsewhere
                WHERE is_team = true
           );
END;
