from liberapay.testing import Harness
from liberapay.utils.emails import jinja_env_html, SimplateLoader


class TestNotifications(Harness):

    def test_add_notifications(self):
        alice = self.make_participant('alice')
        alice.add_notification('abcd')
        alice.add_notification('1234')
        assert alice.pending_notifs == 2

    def test_remove_notification(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.add_notification('abcd')
        id = alice.add_notification('1234')
        alice.add_notification('bcde')

        # check that bob can't remove alice's notification
        bob.remove_notification(id)
        alice = alice.from_id(alice.id)
        assert alice.pending_notifs == 3

        alice.remove_notification(id)
        assert alice.pending_notifs == 2

    def test_render_notifications(self):
        self.client.website.emails['test_event'] = {
            'subject': 'Test notification',
            'text/html': SimplateLoader(None, """
                Test that builtins are available: len([]) = {{ len([]) }}.
                Test escaping: {{ _("{0}", '<test-escaping>'|safe) }}
            """).load(jinja_env_html, None)
        }
        alice = self.make_participant('alice')
        alice.add_notification('test_event')
        alice.add_notification(
            'team_invite',
            team='team',
            team_url='fake_url',
            inviter='bob',
        )
        r = self.client.GET('/alice/notifications.html', auth_as=alice).text
        assert ' len([]) = 0.' in r
        assert '<a href="fake_url"' in r
        assert 'bob' in r
        assert ' alert-&lt;type ' not in r
        assert 'alert-info' in r
        assert '<test-escaping>' in r, r

    def test_render_unknown_notification(self):
        alice = self.make_participant('alice')
        alice.add_notification('fake_event_name')
        r = self.client.GET('/alice/notifications.html', auth_as=alice,
                            sentry_reraise=False).text
        assert 'fake_event_name' not in r

    def test_marking_notification_as_read_requires_until_id(self):
        """
        As described in https://github.com/liberapay/liberapay.com/issues/136,
        this is to avoid a race condition where new notifications created,
        but the user did not see them when marking as read

        To solve that, we simply pass the maximum id we want to mark as read
        """
        alice = self.make_participant('alice')
        # n1 = alice.add_notification('low_balance')
        # n2 = alice.add_notification('low_balance')
        #
        # assert alice.pending_notifs == 2

        r = self.client.PxST('/alice/notifications.json', auth_as=alice,
                             data={'mark_all_as_read': 'true'})
        assert r.code == 400

        n1 = alice.add_notification('low_balance')
        n2 = alice.add_notification('low_balance')

        assert alice.pending_notifs == 2

        r = self.client.PxST('/alice/notifications.json', auth_as=alice,
                             data={
                                'mark_all_as_read': 'true',
                                'until': str(n1)})

        assert r.code == 302

        notifications = self.db.all("""
            SELECT id, event, context, is_new
              FROM notification_queue
             WHERE participant = %s
               AND is_new = true
          ORDER BY id DESC
        """, (alice.id,))
        assert len(notifications) == 1
        assert notifications[0].id == n2
