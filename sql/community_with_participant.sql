CREATE TYPE community_with_participant AS
( id             bigint
, name           text
, nmembers       int
, nsubscribers   int
, ctime          timestamptz
, creator        bigint
, lang           text
, participant    participants
);

CREATE OR REPLACE FUNCTION load_participant_for_community (communities)
RETURNS community_with_participant
AS $$
    SELECT $1.id
         , $1.name
         , $1.nmembers
         , $1.nsubscribers
         , $1.ctime
         , $1.creator
         , $1.lang
         , participants.*::participants
      FROM participants
     WHERE participants.id = $1.participant;
$$ LANGUAGE SQL;

CREATE CAST (communities AS community_with_participant)
    WITH FUNCTION load_participant_for_community(communities);
