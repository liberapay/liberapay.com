BEGIN;
    UPDATE exchange_routes AS r
       SET is_default = null
     WHERE is_default
       AND NOT EXISTS (
               SELECT 1
                 FROM events e
                WHERE e.participant = r.participant
                  AND e.type = 'set_default_route'
                  AND e.payload = jsonb_build_object(
                          'id', r.id,
                          'network', r.network
                      )
           );
END;
