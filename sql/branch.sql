DELETE FROM elsewhere WHERE platform in ('facebook', 'google');
DELETE FROM app_conf WHERE key LIKE 'facebook_%';
