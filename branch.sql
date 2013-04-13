-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/449

DROP TABLE IF EXISTS identifications;
DROP TABLE IF EXISTS brands;
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS tips_to_brands;

BEGIN;

    CREATE TABLE brands
    ( id            bigserial   PRIMARY KEY
    , name          text        NOT NULL UNIQUE
    , slug          text        NOT NULL UNIQUE
    , url           text        NOT NULL UNIQUE
    , description   text        NOT NULL DEFAULT ''
    , company_id    bigint      NOT NULL REFERENCES companies
                                 ON DELETE RESTRICT ON UPDATE RESTRICT
     );

    INSERT INTO brands (name, slug, url, description, company_id)
         SELECT 'Gittip'
              , 'gittip'
              , 'https://www.gittip.com/'
              , '<a href="/">Gittip</a> is a weekly gift exchange. ' ||
                'It is funded on itself.'
              , id
           FROM companies
          WHERE username='gittip';

    CREATE TABLE identifications
    ( id                bigserial   PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , brand_id          bigint      NOT NULL REFERENCES brands
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
    , participant_id    bigint      NOT NULL REFERENCES participants (id)
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
    , weight            numeric(17, 16) NOT NULL
    , identified_by     bigint      NOT NULL REFERENCES participants (id)
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
     );

    CREATE TABLE tips_for_brands
    ( id        serial                      PRIMARY KEY
    , ctime     timestamp with time zone    NOT NULL
    , mtime     timestamp with time zone    NOT NULL
                                             DEFAULT CURRENT_TIMESTAMP
    , tipper    bigint          NOT NULL REFERENCES participants (id)
                                 ON DELETE RESTRICT ON UPDATE RESTRICT
    , tippee    bigint          NOT NULL REFERENCES participants (id)
                                 ON DELETE RESTRICT ON UPDATE RESTRICT
    , amount    numeric(35,2)   NOT NULL
     );

END;
