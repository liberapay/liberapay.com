CREATE TYPE community_with_participant AS
( c communities
, p participants
);

CREATE OR REPLACE FUNCTION load_participant_for_community (communities)
RETURNS community_with_participant
AS $$
    SELECT $1, p
      FROM participants p
     WHERE p.id = $1.participant;
$$ LANGUAGE SQL;

CREATE CAST (communities AS community_with_participant)
    WITH FUNCTION load_participant_for_community(communities);
