DELETE FROM notification_queue WHERE event IN ('income', 'low_balance');
