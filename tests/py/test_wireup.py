import unittest
from unittest.mock import patch


class Test(unittest.TestCase):

    def test_01_full_algorithm_doesnt_fail_when_db_is_down(self):
        with patch.dict('os.environ', {'DATABASE_URL': 'dbname=nonexistent'}):
            from liberapay.website import website
            from liberapay.wireup import full_algorithm
            full_algorithm.run(**website.__dict__)

    def test_99_main_is_reentrant(self):
        from liberapay.main import website
        assert website
        from liberapay.main import website
        assert website
