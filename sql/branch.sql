ALTER TABLE participants ALTER COLUMN email_notif_bits SET DEFAULT 2147483646;
UPDATE notifications SET web = false WHERE event = 'income~v2';

CREATE SEQUENCE polls_id_seq
START WITH 1
INCREMENT BY 1
MINVALUE 1
MAXVALUE 922337203685475807
NO CYCLE;

CREATE TABLE polls (
	id bigint UNIQUE DEFAULT nextval('polls_id_seq'::regclass) NOT NULL,
	name Text NOT NULL,
	start_date timestamp NOT NULL,
	end_date timestamp NOT NULL,
	creator bigint NOT NULL,
	description Text,
	n_participants bigint NOT NULL,
	type smallint NOT NULL,
 	community_id bigint NOT NULL REFERENCES communities(id)
);

ALTER SEQUENCE polls_id_seq OWNED BY polls.id;

CREATE SEQUENCE poll_vote_options_id_seq
START WITH 1
INCREMENT BY 1
MINVALUE 1
MAXVALUE 922337203685475807
NO CYCLE;

CREATE TABLE poll_vote_options (
	id bigint UNIQUE DEFAULT nextval('poll_vote_options_id_seq'::regclass) NOT NULL,
	poll_id bigint NOT NULL REFERENCES polls(id),
	name Text NOT NULL,
	count bigint NOT NULL
);

ALTER SEQUENCE poll_vote_options_id_seq OWNED BY poll_vote_options.id;

CREATE TABLE poll_participants (
	poll_id bigint NOT NULL REFERENCES polls(id),
	participant_id bigint NOT NULL REFERENCES identities(id),
	is_voting boolean NOT NULL,
	voted_on_option bigint NOT NULL REFERENCES poll_vote_options(id)
)
