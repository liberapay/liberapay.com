SELECT 'after deployment';

UPDATE emails SET verified = null WHERE participant IS null AND verified IS true;
