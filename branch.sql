-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/287


-- participants
ALTER TABLE participants RENAME COLUMN id TO username;


-- elsewhere
ALTER TABLE elsewhere RENAME COLUMN participant_id TO participant;

ALTER TABLE "elsewhere" DROP CONSTRAINT "elsewhere_participant_id_fkey";
ALTER TABLE "elsewhere" ADD CONSTRAINT "elsewhere_participant_fkey"
    FOREIGN KEY (participant) REFERENCES participants(username)
    ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE "elsewhere" DROP CONSTRAINT
                                      "elsewhere_platform_participant_id_key";
ALTER TABLE "elsewhere" ADD CONSTRAINT "elsewhere_platform_participant_key"
    UNIQUE (platform, participant);


-- exchanges
ALTER TABLE exchanges RENAME COLUMN participant_id TO participant;

ALTER TABLE "exchanges" DROP CONSTRAINT "exchanges_participant_id_fkey";
ALTER TABLE "exchanges" ADD CONSTRAINT "exchanges_participant_fkey"
    FOREIGN KEY (participant) REFERENCES participants(username)
    ON UPDATE CASCADE ON DELETE RESTRICT;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/680

ALTER TABLE participants ADD COLUMN id bigserial NOT NULL UNIQUE;
