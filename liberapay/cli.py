from liberapay import wireup


def payday():

    # Wire things up.
    # ===============

    env = wireup.env()
    db = wireup.db(env)

    wireup.billing(env)


    # Lazily import the billing module.
    # =================================

    from liberapay.billing.exchanges import sync_with_balanced
    from liberapay.billing.payday import Payday

    try:
        sync_with_balanced(db)
        Payday.start().run()
    except KeyboardInterrupt:
        pass
    except:
        import aspen
        import traceback
        aspen.log(traceback.format_exc())
