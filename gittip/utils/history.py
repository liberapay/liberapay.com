def iter_payday_events(db, participant):
    """Yields payday events for the given participant.
    """
    username = participant.username
    exchanges = db.all("""
        SELECT *
          FROM exchanges
         WHERE participant=%s
    """, (username,), back_as=dict)
    transfers = db.all("""
        SELECT *
          FROM transfers
         WHERE tipper=%(username)s OR tippee=%(username)s
    """, locals(), back_as=dict)

    if not (exchanges or transfers):
        return

    payday_dates = db.all("""
        SELECT ts_start::date
          FROM paydays
      ORDER BY ts_start ASC
    """)

    balance = participant.balance
    prev_date = None
    get_timestamp = lambda e: e['timestamp']
    events = sorted(exchanges+transfers, key=get_timestamp, reverse=True)
    for event in events:

        event['balance'] = balance

        event_date = event['timestamp'].date()
        if event_date != prev_date:
            if prev_date:
                yield dict(kind='day-close', balance=balance)
            day_open = dict(kind='day-open', date=event_date, balance=balance)
            if payday_dates:
                while payday_dates and payday_dates[-1] > event_date:
                    payday_dates.pop()
                payday_date = payday_dates[-1] if payday_dates else None
                if event_date == payday_date:
                    day_open['payday_number'] = len(payday_dates) - 1
            yield day_open
            prev_date = event_date

        if 'fee' in event:
            if event['amount'] > 0:
                kind = 'charge'
                balance -= event['amount']
            else:
                kind = 'credit'
                balance -= event['amount'] - event['fee']
        else:
            kind = 'transfer'
            if event['tippee'] == username:
                balance -= event['amount']
            else:
                balance += event['amount']
        event['kind'] = kind

        yield event

    yield dict(kind='day-close', balance='0.00')
