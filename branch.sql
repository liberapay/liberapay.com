BEGIN;
	UPDATE participants SET anonymous_receiving=FALSE WHERE number='plural';
END;