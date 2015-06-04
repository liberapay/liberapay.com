

def ba_withdrawal_failed(_, user):
    href = '/%s/routes/bank-account.html' % user.username
    return ('error',
        ['a',
            {'href': href}, _("The transfer to your bank account has failed!"),
        ],
    )


def credit_card_failed(_, user):
    href = '/%s/routes/credit-card.html' % user.username
    return ('error',
        ['span', _("Your credit card has failed!") + " ",
            ['a', {'href': href}, _("Fix your card")]
        ],
    )


def pledgee_joined(_, user_name, platform, profile_url):
    return ('notice',
        ['a',
            {'href': profile_url},
            _("{0} from {1} has joined Liberapay!", user_name, platform),
        ],
    )
