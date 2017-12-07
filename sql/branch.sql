CREATE OR REPLACE FUNCTION round(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round($1.amount, 2), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION convert(currency_amount, currency, boolean) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
        result currency_amount;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        rate := (
            SELECT r.rate
              FROM currency_exchange_rates r
             WHERE r.source_currency = $1.currency
        );
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        result := ($1.amount / rate, $2);
        RETURN (CASE WHEN $3 THEN round(result) ELSE result END);
    END;
$$ LANGUAGE plpgsql STRICT;

CREATE OR REPLACE FUNCTION convert(currency_amount, currency) RETURNS currency_amount AS $$
    BEGIN RETURN convert($1, $2, true); END;
$$ LANGUAGE plpgsql STRICT;

CREATE OR REPLACE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN RETURN ($1.amount + (convert($2, $3, false)).amount, $3); END;
$$ LANGUAGE plpgsql STRICT;

DROP AGGREGATE sum(currency_amount, currency);
CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
    finalfunc = round,
    stype = currency_amount,
    initcond = '(0,)'
);

CREATE OR REPLACE FUNCTION currency_amount_fuzzy_avg_sfunc(
    currency_amount_fuzzy_avg_state, currency_amount, currency
) RETURNS currency_amount_fuzzy_avg_state AS $$
    BEGIN
        IF ($2.currency = $3) THEN
            RETURN ($1._sum + $2.amount, $1._count + 1, $3);
        END IF;
        RETURN ($1._sum + (convert($2, $3, false)).amount, $1._count + 1, $3);
    END;
$$ LANGUAGE plpgsql STRICT;

CREATE OR REPLACE FUNCTION currency_amount_fuzzy_avg_ffunc(currency_amount_fuzzy_avg_state)
RETURNS currency_amount AS $$
    BEGIN RETURN round(
        ((CASE WHEN $1._count = 0 THEN 0 ELSE $1._sum / $1._count END), $1.target)::currency_amount
    ); END;
$$ LANGUAGE plpgsql STRICT;
