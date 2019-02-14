from liberapay.testing import Harness
from liberapay.utils.emails import jinja_env_html, SimplateLoader


class TestNotifications(Harness):

    def test_add_notifications(self):
        alice = self.make_participant('alice')
        alice.notify('abcd', email=False)
        alice.notify('1234', email=False)
        assert alice.pending_notifs == 2

    def test_remove_notification(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.notify('abcd', email=False)
        id = alice.notify('1234', email=False)
        alice.notify('bcde', email=False)

        # check that bob can't remove alice's notification
        bob.remove_notification(id)
        alice = alice.from_id(alice.id)
        assert alice.pending_notifs == 3

        alice.remove_notification(id)
        assert alice.pending_notifs == 2

    def test_render_notifications(self):
        self.client.website.emails['test_event'] = {
            'subject': SimplateLoader(None, """
                Test notification subject
            """).load(jinja_env_html, None),
            'text/html': SimplateLoader(None, """
                Test that builtins are available: len([]) = {{ len([]) }}.
                Test escaping: {{ _("{0}", '<test-escaping>'|safe) }}
            """).load(jinja_env_html, None)
        }
        alice = self.make_participant('alice')
        alice.notify('test_event', email=False)
        alice.notify(
            'team_invite',
            email=False,
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
        assert 'Test notification subject' in r

    def test_render_unknown_notification(self):
        alice = self.make_participant('alice')
        alice.notify('fake_event_name', email=False)
        r = self.client.GET('/alice/notifications.html', auth_as=alice,
                            sentry_reraise=False).text
        assert 'fake_event_name' not in r

    def test_marking_notifications_as_read_avoids_race_condition(self):
        alice = self.make_participant('alice')
        n1 = alice.notify(
            'team_invite',
            email=False,
            team='team',
            team_url='fake_url',
            inviter='bob',
        )
        n2 = alice.notify(
            'team_invite',
            email=False,
            team='teamX',
            team_url='fake_url',
            inviter='Zarina',
        )
        assert alice.pending_notifs == 2

        data = {'mark_all_as_read': 'true', 'until': str(n1)}
        r = self.client.PxST('/alice/notifications.json', data, auth_as=alice)
        assert r.code == 302

        notifications = self.db.all("""
            SELECT id, event, context, is_new
              FROM notifications
             WHERE participant = %s
               AND is_new = true
               AND web
          ORDER BY id DESC
        """, (alice.id,))
        assert len(notifications) == 1
        assert notifications[0].id == n2
