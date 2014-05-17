BEGIN;

    ALTER TABLE elsewhere ALTER COLUMN user_name DROP NOT NULL;

    UPDATE elsewhere
       SET display_name = user_name
         , user_name = NULL
     WHERE platform = 'bountysource';

END;
