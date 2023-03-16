CREATE TABLE cron_jobs
( name                text          PRIMARY KEY
, last_start_time     timestamptz
, last_success_time   timestamptz
, last_error_time     timestamptz
, last_error          text
);
