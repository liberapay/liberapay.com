from os.path import abspath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aspen import resources

from liberapay.constants import EPOCH
from liberapay.testing import Harness


initial_data = dict(
    id='-1',
    username='alice',
    email_address='alice@example.net',
    session_token='foobar',
)

gratipay_response = SimpleNamespace(
    json=lambda: dict(
        initial_data,
        anonymous_giving=False,
        avatar_url='https://example.net/alice/avatar',
        email_lang='en',
        is_searchable=True,
        email_addresses=[
            dict(
                address=initial_data['email_address'],
                verified=True,
                verification_start=EPOCH,
                verification_end=EPOCH,
            ),
        ],
        payment_instructions=[dict()],  # TODO
        elsewhere=[dict()],  # TODO
        statements=[dict()],  # TODO
        teams=[dict()],  # TODO
    ),
    status_code=200,
)

class TestMigrate(Harness):

    def test_migrate(self):
        # Step 1
        r = self.client.POST('/migrate', initial_data)
        assert r.code == 200
        assert "Welcome, alice!" in r.text, r.text
        # Step 2
        cache_entry = resources.__cache__[abspath('www/migrate.spt')]
        simplate_context = cache_entry.resource.pages[0]
        requests = MagicMock()
        requests.post.return_value = gratipay_response
        with patch.dict(simplate_context, {'requests': requests}):
            r = self.client.PxST('/migrate?step=2', initial_data, sentry_reraise=False)
            assert r.code == 302
            assert r.headers[b'Location'] == b'?step=3'
        # Step 3
        r = self.client.GET('/migrate?step=3', cookies=r.headers.cookie)
        assert r.code == 200

    def test_migrate_without_initial_data(self):
        r = self.client.POST('/migrate', {k: '' for k in initial_data})
        assert r.code == 200
        assert "Oops, you need to go back to Gratipay " in r.text, r.text
