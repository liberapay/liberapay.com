-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/449

CREATE TABLE companies
( id                    bigserial   PRIMARY KEY
, brand_id              bigint      NOT NULL REFERENCES brands
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
, voter_id              bigint      NOT NULL REFERENCES participants.id
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
, candidate_id          bigint      NOT NULL REFERENCES participants.id
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
, vote                  int         NOT NULL
 );

CREATE TABLE brands
( id                    bigserial   PRIMARY KEY
, name                  text        NOT NULL
, name_lower            text        NOT NULL
, url                   text        NOT NULL
, company_id            bigint      NOT NULL REFERENCES companies
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
 );

CREATE TABLE identifications
( id                    bigserial   PRIMARY KEY
, brand_id              bigint      NOT NULL REFERENCES brands
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
, identifier_id         bigint      NOT NULL REFERENCES participants.id
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
, identified_id         bigint      NOT NULL REFERENCES participants.id
                                     ON DELETE RESTRICT ON UPDATE RESTRICT
, weight                int         NOT NULL
 );
