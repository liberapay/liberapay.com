-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/703

ALTER TABLE paydays
   ADD COLUMN nactive bigint DEFAULT 0;

UPDATE paydays SET nactive=(
    SELECT count(DISTINCT foo.*) FROM (
        SELECT tipper FROM transfers WHERE "timestamp" >= ts_start AND "timestamp" < ts_end
            UNION
        SELECT tippee FROM transfers WHERE "timestamp" >= ts_start AND "timestamp" < ts_end
        ) AS foo
);
