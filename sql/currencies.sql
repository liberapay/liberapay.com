-- Base types

CREATE TYPE currency AS ENUM ('EUR', 'USD');
CREATE TYPE currency_amount AS (amount numeric, currency currency);


-- Arithmetic operators

CREATE FUNCTION currency_amount_add(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount + $2.amount, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR + (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_add,
    commutator = +
);

CREATE FUNCTION currency_amount_sub(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount - $2.amount, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_sub
);

CREATE FUNCTION currency_amount_neg(currency_amount)
RETURNS currency_amount AS $$
    BEGIN RETURN (-$1.amount, $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    rightarg = currency_amount,
    procedure = currency_amount_neg
);


-- Aggregate functions

CREATE AGGREGATE sum(currency_amount) (
    sfunc = currency_amount_add,
    stype = currency_amount
);


-- Convenience functions

CREATE FUNCTION zero(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (0::numeric, $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;


-- Comparison operators

CREATE FUNCTION currency_amount_eq(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN ($1.currency = $2.currency AND $1.amount = $2.amount); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR = (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_eq,
    commutator = =
);

CREATE FUNCTION currency_amount_ne(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN ($1.currency <> $2.currency OR $1.amount <> $2.amount); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <> (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_ne,
    commutator = <>
);

CREATE FUNCTION currency_amount_gt(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount > $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR > (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_gt,
    commutator = <,
    negator = <=
);

CREATE FUNCTION currency_amount_gte(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount >= $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR >= (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_gte,
    commutator = <=,
    negator = <
);

CREATE FUNCTION currency_amount_lt(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount < $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR < (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_lt,
    commutator = >,
    negator = >=
);

CREATE FUNCTION currency_amount_lte(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount <= $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <= (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_lte,
    commutator = >=,
    negator = >
);

CREATE FUNCTION currency_amount_eq_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount = $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR = (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_eq_numeric,
    commutator = =
);

CREATE FUNCTION currency_amount_ne_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount <> $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <> (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_ne_numeric,
    commutator = <>
);

CREATE FUNCTION currency_amount_gt_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount > $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR > (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_gt_numeric,
    commutator = <,
    negator = <=
);

CREATE FUNCTION currency_amount_gte_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount >= $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR >= (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_gte_numeric,
    commutator = <=,
    negator = <
);

CREATE FUNCTION currency_amount_lt_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount < $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR < (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_lt_numeric,
    commutator = >,
    negator = >=
);

CREATE FUNCTION currency_amount_lte_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount <= $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <= (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_lte_numeric,
    commutator = >=,
    negator = >
);


-- Exchange rates

CREATE TABLE currency_exchange_rates
( source_currency   currency   NOT NULL
, target_currency   currency   NOT NULL
, rate              numeric    NOT NULL
, UNIQUE (source_currency, target_currency)
);


-- Currency conversion function

CREATE FUNCTION convert(currency_amount, currency) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
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
        RETURN ($1.amount / rate, $2);
    END;
$$ LANGUAGE plpgsql STRICT;
