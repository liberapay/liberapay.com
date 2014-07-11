from decimal import Decimal

from aspen import log


def iter_payday_events(db, participant):
    """Yields payday events for the given participant username.

    Each payday is expected to encompass 0 or 1 exchanges and 0 or more
    transfers per participant. Here we knit them together along with start
    and end events for each payday. If we have exchanges or transfers that
    fall outside of a payday, then we have a logic bug. I am 50% confident
    that this will manifest some day.

    """
    username = participant.username
    paydays = db.all("""
        SELECT ts_start, ts_end
          FROM paydays
      ORDER BY ts_start DESC
    """, back_as=dict)
    npaydays = len(paydays)
    exchanges = db.all("""
        SELECT *
          FROM exchanges
         WHERE participant=%s
      ORDER BY timestamp ASC
    """, (username,), back_as=dict)
    transfers = db.all("""
        SELECT *
          FROM transfers
         WHERE tipper=%(username)s OR tippee=%(username)s
      ORDER BY timestamp ASC
    """, locals(), back_as=dict)
    balance = participant.balance
    for i, payday in enumerate(paydays, 1):

        if not (exchanges or transfers):
            # Show all paydays since the user started really participating.
            break

        payday_start = { 'event': 'payday-start'
                       , 'timestamp': payday['ts_start']
                       , 'number': npaydays - i
                       , 'balance': Decimal('0.00')
                        }
        payday_end = { 'event': 'payday-end'
                     , 'timestamp': payday['ts_end']
                     , 'number': npaydays - i
                      }

        events = []
        while (exchanges or transfers):

            # Take the next event, either an exchange or transfer.
            # ====================================================
            # We do this by peeking at both lists, and popping the list
            # that has the next event.

            exchange = exchanges[-1] if exchanges else None
            transfer = transfers[-1] if transfers else None

            if exchange is None:
                event = transfers.pop()
            elif transfer is None:
                event = exchanges.pop()
            elif transfer['timestamp'] > exchange['timestamp']:
                event = transfers.pop()
            else:
                event = exchanges.pop()

            if 'fee' in event:
                if event['amount'] > 0:
                    event['event'] = 'charge'
                else:
                    event['event'] = 'credit'
            else:
                event['event'] = 'transfer'

            # Record the next event.
            # ======================

            if event['timestamp'] < payday_start['timestamp']:
                if event['event'] == 'exchange':
                    back_on = exchanges
                else:
                    back_on = transfers
                back_on.append(event)
                break

            events.append(event)

        if not events:
            continue

        # Calculate balance.
        # ==================

        prev = events[0]
        prev['balance'] = balance
        for event in events[1:] + [payday_start]:
            if prev['event'] == 'charge':
                balance = prev['balance'] - prev['amount']
            elif prev['event'] == 'credit':
                balance = prev['balance'] - prev['amount'] + prev['fee']
            elif prev['event'] == 'transfer':
                if prev['tippee'] == username:
                    balance = prev['balance'] - prev['amount']
                else:
                    balance = prev['balance'] + prev['amount']
            event['balance'] = balance
            prev = event
        balance = payday_start['balance']

        yield payday_start
        for event in reversed(events):
            yield event
        yield payday_end

    # This should catch that logic bug.
    if exchanges or transfers:
        log("These should be empty:", exchanges, transfers)
        raise Exception("Logic bug in payday timestamping.")
