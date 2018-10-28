ALTER TABLE emails DROP CONSTRAINT emails_participant_address_key;
CREATE UNIQUE INDEX emails_participant_address_key ON emails (participant, lower(address));
