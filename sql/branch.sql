BEGIN;

    CREATE TABLE newsletters
    ( id              bigserial     PRIMARY KEY
    , ctime           timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP
    , sender          bigint        NOT NULL REFERENCES participants
    );

    CREATE TABLE newsletter_texts
    ( id              bigserial     PRIMARY KEY
    , newsletter      bigint        NOT NULL REFERENCES newsletters
    , lang            text          NOT NULL
    , subject         text          NOT NULL CHECK (subject <> '')
    , body            text          NOT NULL CHECK (body <> '')
    , ctime           timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP
    , scheduled_for   timestamptz
    , sent_at         timestamptz
    , UNIQUE (newsletter, lang)
    );

    CREATE INDEX newsletter_texts_not_sent_idx
              ON newsletter_texts (scheduled_for ASC)
           WHERE sent_at IS NULL AND scheduled_for IS NOT NULL;

END;
