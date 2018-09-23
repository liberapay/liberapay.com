DROP INDEX email_blacklist_report_key;
CREATE UNIQUE INDEX email_blacklist_report_key ON email_blacklist (report_id, address);
