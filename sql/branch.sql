BEGIN;
    ALTER TABLE payin_transfer_events
        ALTER COLUMN status TYPE payin_transfer_status USING status::text::payin_transfer_status;
    WITH updated AS (
        UPDATE payin_transfers pt
           SET status = 'pending'
          FROM payins pi
         WHERE pi.id = pt.payin
           AND pi.status = 'pending'
           AND pt.status = 'pre'
     RETURNING pt.*
    )
    INSERT INTO payin_transfer_events
                (payin_transfer, status, error, timestamp)
         SELECT pt.id, pt.status, pt.error, current_timestamp
           FROM updated pt;
END;
