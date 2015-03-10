from datetime import datetime
from decimal import Decimal

from psycopg2 import IntegrityError


def get_end_of_year_balance(db, participant, year, current_year):
    if year == current_year:
        return participant.balance
    if year < participant.claimed_time.year:
        return Decimal('0.00')

    balance = db.one("""
        SELECT balance
          FROM balances_at
         WHERE participant = %s
           AND "at" = %s
    """, (participant.id, datetime(year+1, 1, 1)))
    if balance is not None:
        return balance

    username = participant.username
    start_balance = get_end_of_year_balance(db, participant, year-1, current_year)
    delta = db.one("""
        SELECT (
                  SELECT COALESCE(sum(amount), 0) AS a
                    FROM exchanges
                   WHERE participant = %(username)s
                     AND extract(year from timestamp) = %(year)s
                     AND amount > 0
                     AND (status is null OR status = 'succeeded')
               ) + (
                  SELECT COALESCE(sum(amount-fee), 0) AS a
                    FROM exchanges
                   WHERE participant = %(username)s
                     AND extract(year from timestamp) = %(year)s
                     AND amount < 0
                     AND (status is null OR status <> 'failed')
               ) + (
                  SELECT COALESCE(sum(-amount), 0) AS a
                    FROM transfers
                   WHERE tipper = %(username)s
                     AND extract(year from timestamp) = %(year)s
               ) + (
                  SELECT COALESCE(sum(amount), 0) AS a
                    FROM transfers
                   WHERE tippee = %(username)s
                     AND extract(year from timestamp) = %(year)s
               ) AS delta
    """, locals())
    balance = start_balance + delta
    try:
        db.run("""
            INSERT INTO balances_at
                        (participant, at, balance)
                 VALUES (%s, %s, %s)
        """, (participant.id, datetime(year+1, 1, 1), balance))
    except IntegrityError:
        pass
    return balance


def iter_payday_events(db, participant, year=None):
    """Yields payday events for the given participant.
    """
    current_year = datetime.utcnow().year
    year = year or current_year

    username = participant.username
    exchanges = db.all("""
        SELECT *
          FROM exchanges
         WHERE participant=%(username)s
           AND extract(year from timestamp) = %(year)s
    """, locals(), back_as=dict)
    transfers = db.all("""
        SELECT *
          FROM transfers
         WHERE (tipper=%(username)s OR tippee=%(username)s)
           AND extract(year from timestamp) = %(year)s
    """, locals(), back_as=dict)

    if not (exchanges or transfers):
        return

    if transfers:
        yield dict(
            kind='totals',
            given=sum(t['amount'] for t in transfers if t['tipper'] == username and t['context'] != 'take'),
            received=sum(t['amount'] for t in transfers if t['tippee'] == username),
        )

    payday_dates = db.all("""
        SELECT ts_start::date
          FROM paydays
      ORDER BY ts_start ASC
    """)

    balance = get_end_of_year_balance(db, participant, year, current_year)
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
                if event['status'] in (None, 'succeeded'):
                    balance -= event['amount']
            else:
                kind = 'credit'
                if event['status'] != 'failed':
                    balance -= event['amount'] - event['fee']
        else:
            kind = 'transfer'
            if event['tippee'] == username:
                balance -= event['amount']
            else:
                balance += event['amount']
        event['kind'] = kind

        yield event

    yield dict(kind='day-close', balance=balance)
