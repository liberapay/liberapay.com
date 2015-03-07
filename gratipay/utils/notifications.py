

def ba_withdrawal_failed(_):
    return ('error',
        ['a',
            {'href': '/bank-account.html'},
            _("The transfer to your bank account has failed!"),
        ],
    )


def credit_card_failed(_):
    return ('error',
        ['span', _("Your credit card has failed!") + " ",
            ['a', {'href': '/credit-card.html'}, _("Fix your card")]
        ],
    )


def credit_card_expires(_):
    return ('error',
        ['span', _("Your credit card is about to expire!") + " ",
            ['a', {'href': '/credit-card.html'}, _("Update card")]
        ],
    )


def email_missing(_, user):
    href = '/%s/account/#emails' % user.participant.username
    return ('notice',
        ['span', _('Your account does not have an associated email address.') + " ",
            ['a', {'href': href}, _('Add an email address')],
        ],
    )
