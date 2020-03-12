BEGIN;
    DROP TRIGGER search_vector_update ON statements;
    ALTER TABLE statements ALTER COLUMN search_conf SET DATA TYPE text USING (search_conf::text);
    CREATE FUNCTION update_tsvector() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector = to_tsvector(NEW.search_conf::regconfig, NEW.content);
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER search_vector_update
        BEFORE INSERT OR UPDATE ON statements
        FOR EACH ROW EXECUTE PROCEDURE
        update_tsvector(search_vector, search_conf, content);
END;
