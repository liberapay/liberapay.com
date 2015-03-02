-- https://github.com/gratipay/gratipay.com/pull/1369
-- The following lets us cast queries to elsewhere_with_participant to get the
-- participant data dereferenced and returned in a composite type along with
-- the elsewhere data.

CREATE TYPE elsewhere_with_participant AS
( id            integer
, platform      text
, user_id       text
, user_name     text
, display_name  text
, email         text
, avatar_url    text
, extra_info    json
, is_team       boolean
, token         json
, participant   participants
 ); -- If Postgres had type inheritance this would be even awesomer.

CREATE FUNCTION load_participant_for_elsewhere (elsewhere)
RETURNS elsewhere_with_participant
AS $$
    SELECT $1.id
         , $1.platform
         , $1.user_id
         , $1.user_name
         , $1.display_name
         , $1.email
         , $1.avatar_url
         , $1.extra_info
         , $1.is_team
         , $1.token
         , participants.*::participants
      FROM participants
     WHERE participants.username = $1.participant
          ;
$$ LANGUAGE SQL;

CREATE CAST (elsewhere AS elsewhere_with_participant)
    WITH FUNCTION load_participant_for_elsewhere(elsewhere);
