BEGIN;
    CREATE TYPE email_status AS ENUM ('queued', 'skipped', 'sending', 'sent', 'failed');
    ALTER TABLE notifications ADD COLUMN email_status email_status;
    UPDATE notifications
       SET email_status = (CASE
               WHEN email_sent = true THEN 'sent'
               WHEN email_sent = false THEN 'skipped'
               WHEN email = true THEN 'queued'
               ELSE null
           END)::email_status
     WHERE email_sent IS NOT null OR email IS true;
    DROP INDEX queued_emails_idx;
    CREATE UNIQUE INDEX queued_emails_idx ON notifications (id ASC)
        WHERE (email AND email_status = 'queued');
END;

SELECT 'after deployment';

BEGIN;
    UPDATE notifications SET email_status = (CASE
               WHEN email_sent = true THEN 'sent'
               WHEN email_sent = false THEN 'skipped'
               ELSE 'queued'
           END)::email_status
     WHERE email IS true
       AND email_status IS null;
    ALTER TABLE notifications DROP COLUMN email_sent;
    ALTER TABLE notifications ADD CONSTRAINT email_chk CHECK (email = (email_status IS NOT null));
END;
