ALTER TYPE transfer_context ADD VALUE 'swap';
ALTER TABLE transfers ADD COLUMN counterpart int REFERENCES transfers;
ALTER TABLE transfers ADD CONSTRAINT counterpart_chk CHECK ((counterpart IS NULL) = (context <> 'swap') OR (context = 'swap' AND status <> 'succeeded'));
