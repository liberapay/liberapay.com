BEGIN;
    UPDATE payins SET error = 'abandoned py payer' WHERE error = 'expired';
    UPDATE payin_events SET error = 'abandoned py payer' WHERE error = 'expired';
    UPDATE payin_transfers SET error = 'abandoned py payer' WHERE error = 'expired';
    UPDATE payin_transfer_events SET error = 'abandoned py payer' WHERE error = 'expired';

    WITH closed as (
        UPDATE participants
           SET status = 'closed'
         WHERE kind = 'group'
           AND status = 'active'
           AND NOT EXISTS (
                   SELECT 1
                     FROM current_takes take
                    WHERE take.team = participants.id
               )
     RETURNING id
    )
    INSERT INTO events (participant, type, payload)
         SELECT id, 'set_status', '"closed"'
           FROM closed;
END;
