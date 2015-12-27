from __future__ import division, print_function, unicode_literals

from collections import namedtuple, OrderedDict


Event = namedtuple('Event', 'name bit title')

_ = lambda a: a
EVENTS = [
    Event('income', 1, _("When I receive money")),
    Event('low_balance', 2, _("When there isn't enough money in my wallet to cover my donations")),
    Event('withdrawal_created', 4, _("When a transfer to my bank account is initiated")),
    Event('withdrawal_failed', 8, _("When a transfer to my bank account fails")),
    Event('pledgee_joined', 16, _("When someone I pledge to joins Liberapay")),
    Event('team_invite', 32, _("When someone invites me to join a team")),
]
del _

# Sanity checks
bits = [e.bit for e in EVENTS]
assert len(set(bits)) == len(bits)  # no duplicates
assert not [b for b in bits if '{0:b}'.format(b).count('1') != 1]  # single bit
del bits

EVENTS = OrderedDict((d.name, d) for d in EVENTS)
EVENTS_S = ' '.join(EVENTS.keys())
