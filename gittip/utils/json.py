

def from_participant(user, username, participant):
    output = { "id": participant.id
             , "username": participant.username
             , "avatar": participant.avatar_url
             , "number": participant.number
             , "on": "gittip"
             , "npatrons": participant.get_number_of_backers()
              }

    # Generate goal key
    # =================
    # Display values:
    #
    #   undefined - user is not here to receive tips, but will generally regift them
    #   null - user has no funding goal
    #   3.00 - user wishes to receive at least this amount

    if participant.goal != 0:
        if participant.goal > 0:
            goal = str(participant.goal)
        else:
            goal = None
        output["goal"] = goal


    # Generate receiving key
    # ===================
    # Display values:
    #
    #   null - user is receiving anonymously
    #   3.00 - user receives this amount in tips

    if not participant.anonymous_receiving:
        receiving = str(participant.get_dollars_receiving())
    else:
        receiving = None
    output["receiving"] = receiving


    # Generate giving key
    # ===================
    # Display values:
    #
    #   null - user is giving anonymously
    #   3.00 - user gives this amount in tips

    if not participant.anonymous_giving:
        giving = str(participant.get_dollars_giving())
    else:
        giving = None
    output["giving"] = giving


    # Generate my_tip key
    # ===================
    # Display values:
    #
    #   undefined - user is not authenticated
    #   "self" - user == participant
    #   null - user has never tipped this person
    #   0.00 - user used to tip this person but now doesn't
    #   3.00 - user tips this person this amount

    if not user.ANON:
        if user.participant.username == username:
            my_tip = "self"
        else:
            my_tip = user.participant.get_tip_to(username)
        output["my_tip"] = str(my_tip)


    # Accounts Elsewhere
    # ==================
    # For Twitter we can use an immutable id. For GitHub we have an immutable id
    # but we can't use it. For Bitbucket we don't have an immutable id. It's nice
    # that Twitter lets us use an immutable id. We should do that ourselves:
    #
    # https://github.com/gittip/www.gittip.com/issues/680


    accounts = participant.get_accounts_elsewhere()
    elsewhere = output['elsewhere'] = {}
    for platform, account in accounts.items():
        fields = ['id', 'user_id', 'user_name']
        elsewhere[platform] = {k: getattr(account, k, None) for k in fields}

    if participant.bitcoin_address is not None:
        output['bitcoin'] = "https://blockchain.info/address/%s" % participant.bitcoin_address

    return output