DELETE FROM app_conf WHERE key = 'trusted_proxies';
ALTER TABLE rate_limiting SET LOGGED;
