from __future__ import division, print_function, unicode_literals


def withdrawal_failed(_, user):
    href = '/%s/routes/bank-account.html' % user.username
    return ('danger',
        ['a',
            {'href': href}, _("The transfer to your bank account has failed!"),
        ]
    )


def withdrawal_pending(_, user, exchange, Money):
    return ('success',
        ['span', _("We have initiated a transfer of {0} from your Liberapay wallet to your bank account.",
                   Money(exchange.amount - exchange.fee, 'USD'))
        ]
    )


def charge_failed(_, user, exchange, Money):
    href = '/%s/routes/credit-card.html' % user.username
    return ('danger',
        ['a', {'href': href},
              _("We tried to charge your credit card {0}, but it failed!",
                Money(exchange.amount + exchange.fee, 'USD'))
        ]
    )


def charge_succeeded(_, user, exchange, Money):
    return ('success',
        ['span', _("We charged your credit card {0} to fund your ongoing donations.",
                   Money(exchange.amount + exchange.fee, 'USD'))
        ]
    )


def pledgee_joined(_, user_name, platform, profile_url):
    return ('info',
        ['a',
            {'href': profile_url},
            _("{0} from {1} has joined Liberapay!", user_name, platform),
        ]
    )
