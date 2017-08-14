BEGIN;
    ALTER TABLE notification_queue
        ADD COLUMN email boolean NOT NULL DEFAULT FALSE,
        ADD COLUMN web boolean NOT NULL DEFAULT TRUE,
        ADD CONSTRAINT destination_chk CHECK (email OR web),
        ADD COLUMN email_sent boolean;
    ALTER TABLE notification_queue RENAME TO notifications;
    CREATE VIEW notification_queue AS SELECT * FROM notifications;
    CREATE UNIQUE INDEX queued_emails_idx ON notifications (id ASC)
        WHERE (email AND email_sent IS NOT true);
END;

SELECT 'after deployment';
BEGIN;
    LOCK TABLE email_queue IN ACCESS EXCLUSIVE MODE;
    DROP VIEW notification_queue;
    ALTER TABLE notifications
        ALTER COLUMN email DROP DEFAULT,
        ALTER COLUMN web DROP DEFAULT;
    WITH deleted AS (
             DELETE FROM email_queue RETURNING *
         ),
         queued_emails AS (
             SELECT e.*, n.id AS notif_id
               FROM deleted e
          LEFT JOIN notifications n ON n.participant = e.participant AND
                                       n.event = e.spt_name AND
                                       n.context = e.context
         ),
         updated AS (
             UPDATE notifications n
                SET email = true
                  , email_sent = false
               FROM queued_emails e
              WHERE n.id = e.notif_id
          RETURNING *
         ),
         inserted AS (
             INSERT INTO notifications
                         (participant, event, context, email, email_sent, web)
                  SELECT participant, spt_name, context, true, false, false
                    FROM queued_emails
                   WHERE notif_id IS NULL
               RETURNING *
         )
    SELECT (SELECT count(*) FROM deleted) AS n_deleted
         , (SELECT count(*) FROM updated) AS n_updated
         , (SELECT count(*) FROM inserted) AS n_inserted;
    DROP TABLE email_queue;
END;
