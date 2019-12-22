import os

import pytest

from liberapay.testing import Harness


@pytest.mark.skipif(
    os.environ.get('LIBERAPAY_PROFILING') != 'yes',
    reason="these tests are only for profiling",
)
class TestPerformance(Harness):

    def test_performance_of_homepage(self):
        for i in range(1000):
            self.client.GET('/')

    def test_performance_when_serving_static_file(self):
        for i in range(10000):
            self.client.GET('/assets/avatar-default.png')
