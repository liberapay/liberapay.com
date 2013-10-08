
DROP TABLE homepage_new_participants;
DROP TABLE homepage_top_givers;
DROP TABLE homepage_top_receivers;
CREATE TABLE homepage_new_participants(username text, claimed_time timestamp with time zone);
CREATE TABLE homepage_top_givers(username text, anonymous boolean, amount numeric);
CREATE TABLE homepage_top_receivers(username text, claimed_time timestamp with time zone, amount numeric);
