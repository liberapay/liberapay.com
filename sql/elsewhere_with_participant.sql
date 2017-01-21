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
