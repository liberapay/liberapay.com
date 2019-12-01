ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'tip-in-arrears';
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'take-in-arrears';

CREATE CAST (current_tips AS tips) WITH INOUT;
\i sql/accounting.sql
