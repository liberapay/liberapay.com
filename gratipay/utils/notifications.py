

def ba_withdrawal_failed(_, user):
    href = '/%s/routes/bank-account.html' % user.participant.username
    return ('error',
        ['a',
            {'href': href}, _("The transfer to your bank account has failed!"),
        ],
    )


def credit_card_failed(_, user):
    href = '/%s/routes/credit-card.html' % user.participant.username
    return ('error',
        ['span', _("Your credit card has failed!") + " ",
            ['a', {'href': href}, _("Fix your card")]
        ],
    )


def credit_card_expires(_, user):
    href = '/%s/routes/credit-card.html' % user.participant.username
    return ('error',
        ['span', _("Your credit card is about to expire!") + " ",
            ['a', {'href': href}, _("Update card")]
        ],
    )


def email_missing(_, user):
    href = '/%s/settings/#emails' % user.participant.username
    return ('notice',
        ['span', _('Your account does not have an associated email address.') + " ",
            ['a', {'href': href}, _('Add an email address')],
        ],
    )
