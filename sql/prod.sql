CREATE OR REPLACE FUNCTION abort_command() RETURNS event_trigger AS $$
    BEGIN
        RAISE EXCEPTION 'command % is disabled', tg_tag;
    END;
$$ LANGUAGE plpgsql;

CREATE EVENT TRIGGER prevent_schema_drop ON ddl_command_start WHEN TAG IN ('DROP SCHEMA')
    EXECUTE PROCEDURE abort_command();
