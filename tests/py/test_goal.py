from liberapay.testing import EUR, Harness


class Tests(Harness):

    def setUp(self):
        self.alice = self.make_participant('alice')

    def change_goal(self, goal, goal_custom="", auth_as="alice", expect_success=False):
        r = self.client.PxST(
            "/alice/edit/goal",
            {'goal': goal, 'goal_custom': goal_custom},
            auth_as=self.alice if auth_as == 'alice' else auth_as
        )
        if expect_success and r.code >= 400:
            raise r
        return r

    def test_wonky_custom_amounts_are_rejected(self):
        r = self.change_goal("custom", ",100,100.0")
        assert r.code == 400
        alice = self.alice.refetch()
        assert alice.goal is None

    def test_anonymous_gets_403(self):
        response = self.change_goal("100.00", auth_as=None)
        assert response.code == 403, response.code

    def test_invalid_is_400(self):
        response = self.change_goal("cheese")
        assert response.code == 400, response.code

    def test_invalid_custom_amount_is_400(self):
        response = self.change_goal("custom", "cheese")
        assert response.code == 400, response.code

    def test_change_goal(self):
        self.change_goal("custom", "100", expect_success=True)
        self.change_goal("0", expect_success=True)
        self.change_goal("-1", "irrelevant", expect_success=True)
        self.change_goal("custom", "1,100.00", expect_success=True)
        self.change_goal("null", "", expect_success=True)
        self.change_goal("custom", "4000", expect_success=True)

        actual = self.db.one("SELECT goal FROM participants")
        assert actual == EUR('4000.00')

        actual = self.db.all("""
            SELECT payload
              FROM events
             WHERE type = 'set_goal'
          ORDER BY ts
        """)
        assert actual == [
            '100.00 EUR',
            '0.00 EUR',
            '-1.00 EUR',
            '1100.00 EUR',
            None,
            '4000.00 EUR',
        ]

    def test_team_member_can_change_team_goal(self):
        team = self.make_participant('team', kind='group')
        team.add_member(self.alice)
        r = self.client.PxST(
            '/team/edit/goal',
            {'goal': 'custom', 'goal_custom': '99.99'},
            auth_as=self.alice
        )
        assert r.code == 302
        assert team.refetch().goal == EUR('99.99')
