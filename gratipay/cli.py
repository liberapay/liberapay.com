"""This is installed as `payday`.
"""
from gratipay import wireup


def payday():

    # Wire things up.
    # ===============

    env = wireup.env()
    db = wireup.db(env)

    wireup.billing(env)
    wireup.nanswers(env)


    # Lazily import the billing module.
    # =================================
    # This dodges a problem where db in billing is None if we import it from
    # gratipay before calling wireup.billing.

    from gratipay.billing.exchanges import sync_with_balanced
    from gratipay.billing.payday import Payday

    try:
        sync_with_balanced(db)
        Payday.start().run()
    except KeyboardInterrupt:
        pass
    except:
        import aspen
        import traceback
        aspen.log(traceback.format_exc())
