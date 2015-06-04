from liberapay.testing import Harness


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
