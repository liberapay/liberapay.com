"""This is installed as `payday`.
"""
from gittip import wireup


def payday():

    # Wire things up.
    # ===============

    env = wireup.env()
    db = wireup.db(env)
    db.run("SET statement_timeout = 0")

    wireup.billing(env)
    wireup.nanswers(env)


    # Lazily import the billing module.
    # =================================
    # This dodges a problem where db in billing is None if we import it from
    # gittip before calling wireup.billing.

    from gittip.billing.exchanges import sync_with_balanced
    from gittip.billing.payday import Payday

    try:
        sync_with_balanced(db)
        Payday.start().run()
    except KeyboardInterrupt:
        pass
    except:
        import aspen
        import traceback
        aspen.log(traceback.format_exc())
