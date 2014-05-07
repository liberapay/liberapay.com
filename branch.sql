-- These changes should be applied after deployment, not before.

BEGIN;

    DROP RULE bitcoin_addresses ON participants;
    DROP RULE log_email_changes ON participants;
    DROP RULE log_participant_number ON participants;

    INSERT INTO events (ts, type, payload)
        SELECT mtime
             , 'participant'
             , concat('{ "id":', p.id
                     ,', "action": "set"'
                     ,', "values":', '{"bitcoin_address": "',b.bitcoin_address,'"}'
                     ,'}')::json
          FROM bitcoin_addresses b
          JOIN participants p ON p.username = participant
      ORDER BY mtime ASC;

    DROP TABLE bitcoin_addresses;

    DROP TABLE emails; -- We don't need to insert events for this one, they already exist.

    INSERT INTO events (ts, type, payload)
        SELECT mtime
             , 'participant'
             , concat('{ "id":', p.id
                     ,', "action": "set"'
                     ,', "values":', '{"number": "',l.number,'"}'
                     ,'}')::json
          FROM log_participant_number l
          JOIN participants p ON p.username = participant
      ORDER BY mtime ASC;

    DROP TABLE log_participant_number;

END;
