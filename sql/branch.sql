CREATE TABLE repositories
( id                    bigserial       PRIMARY KEY
, platform              text            NOT NULL
, remote_id             text            NOT NULL
, owner_id              text            NOT NULL
, name                  text            NOT NULL
, slug                  text            NOT NULL
, description           text
, last_update           timestamptz     NOT NULL
, is_fork               boolean
, stars_count           int
, extra_info            json
, info_fetched_at       timestamptz     NOT NULL DEFAULT now()
, participant           bigint          NOT NULL REFERENCES participants
, show_on_profile       boolean         NOT NULL DEFAULT FALSE
, UNIQUE (platform, remote_id)
, UNIQUE (platform, slug)
);

CREATE INDEX repositories_trgm_idx ON repositories
    USING gist(name gist_trgm_ops);
