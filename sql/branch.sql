BEGIN;
    -- We can't use NULL as default because it would break the unique indexes
    ALTER TABLE elsewhere ADD COLUMN domain text NOT NULL DEFAULT '';
    ALTER TABLE elsewhere ALTER COLUMN domain DROP DEFAULT;

    DROP INDEX elsewhere_lower_platform_idx;
    CREATE UNIQUE INDEX elsewhere_user_name_key ON elsewhere (lower(user_name), platform, domain);

    ALTER TABLE elsewhere DROP CONSTRAINT elsewhere_platform_user_id_key;
    CREATE UNIQUE INDEX elsewhere_user_id_key ON elsewhere (platform, domain, user_id);

    CREATE TABLE oauth_apps
    ( platform   text   NOT NULL
    , domain     text   NOT NULL
    , key        text   NOT NULL
    , secret     text   NOT NULL
    , UNIQUE (platform, domain, key)
    );

    INSERT INTO app_conf (key, value) VALUES
        ('app_name', '"Liberapay Dev"'::jsonb);
END;
