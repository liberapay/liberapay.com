"""This is installed as `payday`.
"""
from gittip import wireup


def payday():
    db = wireup.db()
    wireup.billing()


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
