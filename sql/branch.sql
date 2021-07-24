CREATE OR REPLACE FUNCTION max(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        IF ($2.amount > $1.amount) THEN
            RETURN $2;
        ELSE
            RETURN $1;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OR REPLACE AGGREGATE max(currency_amount) (
    sfunc = max,
    stype = currency_amount
);

CREATE OR REPLACE FUNCTION min(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        IF ($2.amount < $1.amount) THEN
            RETURN $2;
        ELSE
            RETURN $1;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OR REPLACE AGGREGATE min(currency_amount) (
    sfunc = min,
    stype = currency_amount
);
