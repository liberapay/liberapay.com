BEGIN;

    -- https://github.com/gittip/www.gittip.com/issues/2472
    UPDATE participants SET claimed_time=NULL
    WHERE claimed_time IS NOT NULL AND id IN (
        SELECT p.id FROM participants p
        JOIN absorptions a ON p.username = a.archived_as
        WHERE claimed_time IS NOT NULL
    );

END;
