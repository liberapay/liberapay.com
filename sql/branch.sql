ALTER TABLE paydays
    ADD COLUMN transfer_volume_refunded int,
    ADD COLUMN week_deposits_refunded int,
    ADD COLUMN week_withdrawals_refunded int;
