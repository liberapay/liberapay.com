"""This is installed as `payday`.
"""
import logstown


def payday():
    logstown.wire_db()
    logstown.wire_samurai()


    # Lazily import the billing module.
    # =================================
    # This dodges a problem where db in billing is None if we import it from 
    # logstown before calling wire_samurai, and it also dodges:
    #
    #   https://github.com/FeeFighters/samurai-client-python/issues/8

    from logstown import billing 

    try:
        billing.payday()
    except KeyboardInterrupt:
        pass
    except:
        import aspen
        import traceback
        aspen.log(traceback.format_exc())
