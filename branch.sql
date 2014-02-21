BEGIN;

    ALTER TABLE participants RENAME COLUMN balanced_account_uri TO balanced_customer_href;

END;
