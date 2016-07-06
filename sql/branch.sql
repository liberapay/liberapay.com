ALTER TABLE transfers ADD COLUMN refund_ref bigint REFERENCES transfers;
ALTER TABLE exchanges ADD COLUMN refund_ref bigint REFERENCES exchanges;
