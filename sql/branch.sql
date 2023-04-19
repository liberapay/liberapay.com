BEGIN;
    UPDATE payins SET error = '' WHERE error = 'None (code None)';
    UPDATE payin_events SET error = '' WHERE error = 'None (code None)';
END;
