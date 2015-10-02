from __future__ import division, print_function, unicode_literals


def withdrawal_failed(_, user, exchange):
    href = '/%s/receiving/payout?exchange_id=%s' % (user.username, exchange.id)
    return ('danger',
        ['a',
            {'href': href}, _("The transfer to your bank account has failed!"),
        ]
    )


def withdrawal_pending(_, user, exchange, Money):
    return ('success',
        ['span', _("We have initiated a transfer of {0} from your Liberapay wallet to your bank account.",
                   Money(exchange.amount - exchange.fee, 'EUR'))
        ]
    )


def charge_failed(_, user, exchange, Money):
    href = '/%s/giving/payin?exchange_id=%s' % (user.username, exchange.id)
    return ('danger',
        ['a', {'href': href},
              _("We tried to charge your credit card {0}, but it failed!",
                Money(exchange.amount + exchange.fee, 'EUR'))
        ]
    )


def charge_succeeded(_, user, exchange, Money):
    return ('success',
        ['span', _("We charged your credit card {0} to fund your ongoing donations.",
                   Money(exchange.amount + exchange.fee, 'EUR'))
        ]
    )


def pledgee_joined(_, user_name, platform, profile_url):
    return ('info',
        ['a',
            {'href': profile_url},
            _("{0} from {1} has joined Liberapay!", user_name, platform),
        ]
    )


def team_invite(_, team, team_url, inviter):
    return ('info',
        ['span',
            _("{0} has invited you to join the {1} team.", inviter, team),
            " ",
            ['a', {'href': team_url}, _("See the team's profile")],
            " | ",
            ['a', {'href': team_url+'membership/accept'}, _("Accept")],
            " | ",
            ['a', {'href': team_url+'membership/refuse'}, _("Refuse")]
        ]
    )
