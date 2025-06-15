BEGIN;
    CREATE TYPE loss_taker AS ENUM ('provider', 'platform');
    ALTER TABLE payment_accounts
        ADD COLUMN independent boolean DEFAULT true,
        ADD COLUMN loss_taker loss_taker DEFAULT 'provider',
        ADD COLUMN details_submitted boolean,
        ADD COLUMN allow_payout boolean,
        DROP CONSTRAINT payment_accounts_participant_provider_country_is_current_key;
    CREATE INDEX payment_accounts_participant_provider_country_is_current_idx
        ON payment_accounts (participant, provider, country, is_current);
END;
SELECT 'after deployment';
BEGIN;
    ALTER TABLE payment_accounts
        ALTER COLUMN independent DROP DEFAULT,
        ALTER COLUMN loss_taker DROP DEFAULT;
END;
