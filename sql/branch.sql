ALTER TABLE cash_bundles ADD CONSTRAINT in_or_out CHECK ((owner IS NULL) <> (withdrawal IS NULL));
