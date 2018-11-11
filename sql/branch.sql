ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'stripe-sdd';

UPDATE participants
   SET email_notif_bits = email_notif_bits | 64 | 128 | 256 | 512 | 1024
 WHERE email_notif_bits <> (email_notif_bits | 64 | 128 | 256 | 512 | 1024);
