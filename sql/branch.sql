BEGIN;

    UPDATE elsewhere
       SET avatar_url = regexp_replace(avatar_url, '\?s=128$', '?s=160')
     WHERE avatar_url ~ '\?s=128$';

    UPDATE participants
       SET avatar_url = regexp_replace(avatar_url, '\?s=128$', '?s=160')
     WHERE avatar_url ~ '\?s=128$';

END;
