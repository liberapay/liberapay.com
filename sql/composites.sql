-- * Communities

CREATE TYPE community_with_participant AS
( c communities
, p participants
);

CREATE FUNCTION load_participant_for_community (communities)
RETURNS community_with_participant
AS $$
    SELECT $1, p
      FROM participants p
     WHERE p.id = $1.participant;
$$ LANGUAGE SQL;

CREATE CAST (communities AS community_with_participant)
    WITH FUNCTION load_participant_for_community(communities);


-- * Elsewhere

CREATE TYPE elsewhere_with_participant AS
( e elsewhere
, p participants
);

CREATE FUNCTION load_participant_for_elsewhere (elsewhere)
RETURNS elsewhere_with_participant
AS $$
    SELECT $1, p
      FROM participants p
     WHERE p.id = $1.participant;
$$ LANGUAGE SQL;

CREATE CAST (elsewhere AS elsewhere_with_participant)
    WITH FUNCTION load_participant_for_elsewhere(elsewhere);


-- * LocalizedString

CREATE TYPE localized_string AS (string text, lang text);
