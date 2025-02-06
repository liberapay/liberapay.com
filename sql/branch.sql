SELECT 'after deployment';

UPDATE participants SET public_name = null WHERE public_name = '';
