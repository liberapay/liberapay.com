BEGIN;
    UPDATE participants
       SET avatar_url = avatar_url || '?s=160'
     WHERE avatar_url IS NOT NULL
       AND avatar_url <> ''
       AND avatar_url NOT LIKE '%?%';
END;
