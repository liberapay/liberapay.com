BEGIN;

    ALTER TABLE transfers ADD COLUMN as_team_member boolean NOT NULL DEFAULT false;

    UPDATE transfers SET as_team_member = true
        FROM participants WHERE participants.username = transfers.tipper
                            AND participants.number = 'plural';

END;
