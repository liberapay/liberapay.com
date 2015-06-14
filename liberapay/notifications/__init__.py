from __future__ import division, print_function, unicode_literals

from collections import namedtuple, OrderedDict


Event = namedtuple('Event', 'name bit title')

_ = lambda a: a
EVENTS = [
    Event('charge_failed', 1, _("When charging my credit card fails")),
    Event('charge_succeeded', 2, _("When charging my credit card succeeds")),
    Event('withdrawal_pending', 4, _("When a transfer to my bank account is initiated")),
    Event('withdrawal_failed', 8, _("When a transfer to my bank account fails")),
    Event('pledgee_joined', 16, _("When someone I pledge to joins Liberapay")),
]
del _

# Sanity checks
bits = [e.bit for e in EVENTS]
assert len(set(bits)) == len(bits)  # no duplicates
assert not [b for b in bits if '{0:b}'.format(b).count('1') != 1]  # single bit
del bits

EVENTS = OrderedDict((d.name, d) for d in EVENTS)
EVENTS_S = ' '.join(EVENTS.keys())
