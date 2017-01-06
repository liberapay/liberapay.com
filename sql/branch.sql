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
    , sent_count      int
    , UNIQUE (newsletter, lang)
    );

    CREATE INDEX newsletter_texts_not_sent_idx
              ON newsletter_texts (scheduled_for ASC)
           WHERE sent_at IS NULL AND scheduled_for IS NOT NULL;

END;

BEGIN;

    CREATE TABLE subscriptions
    ( id            bigserial      PRIMARY KEY
    , publisher     bigint         NOT NULL REFERENCES participants
    , subscriber    bigint         NOT NULL REFERENCES participants
    , ctime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
    , mtime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
    , is_on         boolean        NOT NULL
    , UNIQUE (publisher, subscriber)
    );

    LOCK TABLE community_subscriptions IN EXCLUSIVE MODE;

    INSERT INTO subscriptions (publisher, subscriber, ctime, mtime, is_on)
         SELECT community, participant, ctime, mtime, is_on
           FROM community_subscriptions
       ORDER BY ctime ASC;

    DROP TABLE community_subscriptions;
    DROP FUNCTION IF EXISTS update_community_nsubscribers();

    ALTER TABLE participants ADD COLUMN nsubscribers int NOT NULL DEFAULT 0;

    LOCK TABLE communities IN EXCLUSIVE MODE;

    UPDATE participants p
       SET nsubscribers = c.nsubscribers
      FROM communities c
     WHERE c.participant = p.id
       AND c.nsubscribers <> p.nsubscribers;

    ALTER TABLE communities DROP COLUMN nsubscribers;

    \i sql/update_counts.sql

    CREATE TRIGGER update_nsubscribers
        BEFORE INSERT OR UPDATE OR DELETE ON subscriptions
        FOR EACH ROW
        EXECUTE PROCEDURE update_nsubscribers();

END;
