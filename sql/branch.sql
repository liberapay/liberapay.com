SELECT 'after deployment';

ALTER TABLE elsewhere DROP COLUMN extra_info;
ALTER TABLE repositories DROP COLUMN extra_info;
