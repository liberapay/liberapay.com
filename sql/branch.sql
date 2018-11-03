BEGIN;

CREATE OR REPLACE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN
        IF ($2.amount IS NULL OR $2.currency IS NULL) THEN RETURN $1; END IF;
        RETURN ($1.amount + (convert($2, $3, false)).amount, $3);
    END;
$$ LANGUAGE plpgsql STRICT;

CREATE OR REPLACE FUNCTION currency_amount_fuzzy_sum_ffunc(currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.amount IS NULL OR $1.currency IS NULL) THEN RETURN NULL; END IF;
        RETURN round($1);
    END;
$$ LANGUAGE plpgsql;

DROP AGGREGATE sum(currency_amount, currency);
CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
    finalfunc = currency_amount_fuzzy_sum_ffunc,
    stype = currency_amount,
    initcond = '(0,)'
);

END;

UPDATE tips
   SET paid_in_advance = NULL
 WHERE paid_in_advance IS NOT NULL
   AND (paid_in_advance).amount IS NULL;
