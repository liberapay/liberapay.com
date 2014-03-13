from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Alice joins a community.
        self.alice = self.make_participant("alice", claimed_time='now', last_bill_result='')
        self.client.POST( '/for/communities.json'
                        , {'name': 'something', 'is_member': 'true'}
                        , auth_as='alice'
                         )

    def test_community_member_shows_up_on_community_listing(self):
        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 2  # entry in New Participants

    def test_givers_show_up_on_community_page(self):

        # Alice tips bob.
        self.make_participant("bob", claimed_time='now')
        self.alice.set_tip_to('bob', '1.00')

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 4  # entries in both New Participants and Givers
        assert 'bob' not in html

    def test_givers_dont_show_up_if_they_give_zero(self):

        # Alice tips bob.
        self.make_participant("bob", claimed_time='now')
        self.alice.set_tip_to('bob', '1.00')
        self.alice.set_tip_to('bob', '0.00')

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 2  # entry in New Participants only
        assert 'bob' not in html

    def test_receivers_show_up_on_community_page(self):

        # Bob tips alice.
        bob = self.make_participant("bob", claimed_time='now', last_bill_result='')
        bob.set_tip_to('alice', '1.00')

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 4  # entries in both New Participants and Receivers
        assert 'bob' not in html

    def test_receivers_dont_show_up_if_they_receive_zero(self):

        # Bob tips alice.
        bob = self.make_participant("bob", claimed_time='now', last_bill_result='')
        bob.set_tip_to('alice', '1.00')
        bob.set_tip_to('alice', '0.00')  # zero out bob's tip

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 2  # entry in New Participants only
        assert 'bob' not in html

    def test_community_listing_works_for_pristine_community(self):
        html = self.client.GET('/for/pristine/', want='response.body')
        assert 'first one here' in html
