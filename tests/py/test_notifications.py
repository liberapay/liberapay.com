from gratipay.testing import Harness

class TestNotifications(Harness):
	def test_add_single_notification(self):
		alice = self.make_participant('alice')
		alice.add_notification('abcd')
		assert alice.notifications == " abcd "

	def test_add_multiple_notifications(self):
		alice = self.make_participant('alice')
		alice.add_notification('abcd')
		alice.add_notification('1234')
		assert alice.notifications == " abcd  1234 "

	def test_add_same_notification_twice(self):
		alice = self.make_participant('alice')
		alice.add_notification('abcd')
		alice.add_notification('abcd')
		assert alice.notifications == " abcd "

	def test_remove_notification(self):
		alice = self.make_participant('alice')
		alice.add_notification('abcd')
		alice.add_notification('1234')
		alice.add_notification('bcde')
		alice.remove_notification('1234')
		assert alice.notifications == " abcd  bcde "
