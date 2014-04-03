"""This is installed as `payday`.
"""
from gittip import wireup


def payday():

    # Wire things up.
    # ===============
    # Manually override max db connections so that we only have one connection.
    # Our db access is serialized right now anyway, and with only one
    # connection it's easier to trust changes to statement_timeout. The point
    # here is that we want to turn off statement_timeout for payday.

    env = wireup.env()
    env.database_maxconn = 1
    db = wireup.db(env)
    db.run("SET statement_timeout = 0")

    wireup.billing(env)
    wireup.nanswers(env)


    # Lazily import the billing module.
    # =================================
    # This dodges a problem where db in billing is None if we import it from
    # gittip before calling wireup.billing.

    from gittip.billing.payday import Payday

    try:
        Payday(db).run()
    except KeyboardInterrupt:
        pass
    except:
        import aspen
        import traceback
        aspen.log(traceback.format_exc())
