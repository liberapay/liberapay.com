from liberapay.testing import Harness
from liberapay.utils.emails import jinja_env_html, SimplateLoader


class TestNotifications(Harness):

    def test_add_notifications(self):
        alice = self.make_participant('alice')
        alice.notify('abcd', email=False)
        alice.notify('1234', email=False)
        assert alice.pending_notifs == 2

    def test_remove_and_restore_notification(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.notify('abcd', email=False)
        n_id = alice.notify('1234', email=False)
        alice.notify('bcde', email=False)

        # check that bob can't remove alice's notification
        r = self.client.PxST('/alice/notifications', {'remove': str(n_id)}, auth_as=bob)
        assert r.code == 403
        alice = alice.refetch()
        assert alice.pending_notifs == 3

        # but alice can
        r = self.client.PxST('/alice/notifications', {'remove': str(n_id)}, auth_as=alice)
        assert r.code == 302
        alice = alice.refetch()
        assert alice.pending_notifs == 2

        # check that bob can't restore alice's notification
        r = self.client.PxST('/alice/notifications', {'restore': str(n_id)}, auth_as=bob)
        assert r.code == 403
        notif = self.db.one("SELECT * FROM notifications WHERE id = %s", (n_id,))
        assert notif.hidden_since is not None

        # but alice can
        r = self.client.PxST('/alice/notifications', {'restore': str(n_id)}, auth_as=alice)
        assert r.code == 302
        notif = self.db.one("SELECT * FROM notifications WHERE id = %s", (n_id,))
        assert notif.hidden_since is None

    def test_render_notifications(self):
        self.client.website.emails['test_event'] = {
            '-/subject': SimplateLoader(None, """
                Test notification subject
            """).load(jinja_env_html, None),
            'text/html': SimplateLoader(None, """
                Test that builtins are available: len([]) = {{ len([]) }}.
                Test escaping: {{ _("{0}", '<test></test>'|safe) }}
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
        assert '<test></test>' in r, r
        assert 'Test notification subject' in r

    def test_render_unknown_notification(self):
        alice = self.make_participant('alice')
        alice.notify('fake_event_name', email=False)
        r = self.client.GET('/alice/notifications.html', auth_as=alice,
                            sentry_reraise=False).text
        assert 'fake_event_name' not in r

    def test_render_broken_notifications(self):
        self.client.website.emails['_broken_subject'] = {
            '-/subject': SimplateLoader(None, "{{ broken }}").load(jinja_env_html, None),
            'text/html': SimplateLoader(None, "").load(jinja_env_html, None)
        }
        self.client.website.emails['_broken_body'] = {
            '-/subject': SimplateLoader(None, "Lorem ipsum").load(jinja_env_html, None),
            'text/html': SimplateLoader(None, "{{ broken }}").load(jinja_env_html, None)
        }
        alice = self.make_participant('alice')
        alice.notify('_broken_subject', email=False)
        alice.notify('_broken_body', email=False)
        r = self.client.GET('/alice/notifications.html', auth_as=alice, sentry_reraise=False)
        assert r.text.count("An error occurred while rendering this notification.") == 2

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

        data = {'mark_all_as_read': 'true', 'last_seen': str(n1)}
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

    def test_marking_a_specific_notification_as_read(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.notify('a', email=False)
        n_id = alice.notify('b', email=False)
        alice.notify('c', email=False)

        # check that bob can't make alice's notification as read
        form_data = {'mark_as_read': str(n_id)}
        r = self.client.PxST('/alice/notifications', form_data, auth_as=bob)
        assert r.code == 403
        alice = alice.refetch()
        assert alice.pending_notifs == 3

        # but alice can
        r = self.client.PxST('/alice/notifications', form_data, auth_as=alice)
        assert r.code == 302
        alice = alice.refetch()
        assert alice.pending_notifs == 2
