CREATE TABLE poll_questions
( id                    bigserial               PRIMARY KEY
, body                  text                    
, created_at            timestamptz             NOT NULL
, updated_at            timestamptz             DEFAULT NULL
)

CREATE TABLE poll_answers
( id                    bigserial               PRIMARY KEY
, body                  text                    
, votes                 int                     DEFAULT 0
, question_id           bigserial               PRIMARY KEY
, created_at            timestamptz             NOT NULL
, updated_at            timestamptz             DEFAULT NULL
, FOREIGN KEY question_id REFERENCES poll_questions(id)
)

CREATE TABLE poll_voting_history
( id                    bigserial               PRIMARY KEY
, question_id           bigserial               UNIQUE KEY
, answer_id             bigserial               UNIQUE KEY              text                    
, usr_id                bigserial               UNIQUE KEY
, created_at            timestamptz             NOT NULL
, updated_at            timestamptz             DEFAULT NULL
, FOREIGN KEY question_id REFERENCES poll_questions(id)
)