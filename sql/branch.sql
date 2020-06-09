BEGIN;
    ALTER TABLE elsewhere DROP CONSTRAINT elsewhere_participant_platform_key;
    CREATE INDEX elsewhere_participant_platform_idx ON elsewhere (participant, platform);
END;
