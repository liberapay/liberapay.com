BEGIN;

CREATE TABLE statements
( participant  bigint  NOT NULL REFERENCES participants(id)
, lang         text    NOT NULL
, content      text    NOT NULL CHECK (content <> '')
, UNIQUE (participant, lang)
);

INSERT INTO statements
    SELECT id, 'en', concat('I am making the world better by ', statement)
      FROM participants
     WHERE statement <> ''
       AND number = 'singular';

INSERT INTO statements
    SELECT id, 'en', concat('We are making the world better by ', statement)
      FROM participants
     WHERE statement <> ''
       AND number = 'plural';

CREATE FUNCTION enumerate(anyarray) RETURNS TABLE (rank bigint, value anyelement) AS $$
    SELECT row_number() over() as rank, value FROM unnest($1) value;
$$ LANGUAGE sql STABLE;

END;
