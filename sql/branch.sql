CREATE FUNCTION currency_amount_mul(numeric, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        RETURN ($2.amount * $1, $2.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR * (
    leftarg = numeric,
    rightarg = currency_amount,
    procedure = currency_amount_mul,
    commutator = *
);

CREATE FUNCTION currency_amount_div(currency_amount, currency_amount)
RETURNS numeric AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN $1.amount / $2.amount;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR / (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_div
);
