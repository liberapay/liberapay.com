DROP VIEW current_exchange_routes CASCADE;

BEGIN;
    ALTER TABLE exchange_routes ADD COLUMN ctime timestamptz;
    UPDATE exchange_routes r
       SET ctime = (
               SELECT min(e.timestamp)
                 FROM exchanges e
                WHERE e.route = r.id
           )
     WHERE ctime IS NULL;
    ALTER TABLE exchange_routes ALTER COLUMN ctime SET DEFAULT now();
END;
