-- ALTER TYPE ... ADD cannot run inside a transaction block
ALTER TYPE transfer_context ADD VALUE 'expense';

BEGIN;

    CREATE TYPE invoice_nature AS ENUM ('expense');

    CREATE TYPE invoice_status AS ENUM
        ('pre', 'canceled', 'new', 'retracted', 'accepted', 'paid', 'rejected');

    CREATE TABLE invoices
    ( id            serial            PRIMARY KEY
    , ctime         timestamptz       NOT NULL DEFAULT CURRENT_TIMESTAMP
    , sender        bigint            NOT NULL REFERENCES participants
    , addressee     bigint            NOT NULL REFERENCES participants
    , nature        invoice_nature    NOT NULL
    , amount        numeric(35,2)     NOT NULL CHECK (amount > 0)
    , description   text              NOT NULL
    , details       text
    , documents     jsonb             NOT NULL
    , status        invoice_status    NOT NULL
    );

    CREATE TABLE invoice_events
    ( id            serial            PRIMARY KEY
    , invoice       int               NOT NULL REFERENCES invoices
    , participant   bigint            NOT NULL REFERENCES participants
    , ts            timestamptz       NOT NULL DEFAULT CURRENT_TIMESTAMP
    , status        invoice_status    NOT NULL
    , message       text
    );

    ALTER TABLE participants ADD COLUMN allow_invoices boolean;

    ALTER TABLE transfers
        ADD COLUMN invoice int REFERENCES invoices,
        ADD CONSTRAINT expense_chk CHECK (NOT (context='expense' AND invoice IS NULL));

    INSERT INTO app_conf VALUES
        ('s3_endpoint', '""'::jsonb),
        ('s3_public_access_key', '""'::jsonb),
        ('s3_secret_key', '""'::jsonb),
        ('s3_region', '"eu-west-1"'::jsonb);

END;
