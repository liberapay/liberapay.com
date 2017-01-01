from datetime import datetime
from decimal import Decimal

from pando import Response
from psycopg2 import IntegrityError

from ..website import website


def get_end_of_year_balance(db, participant, year, current_year):
    if year == current_year:
        return participant.balance
    if year < participant.join_time.year:
        return Decimal('0.00')

    balance = db.one("""
        SELECT balance
          FROM balances_at
         WHERE participant = %s
           AND "at" = %s
    """, (participant.id, datetime(year+1, 1, 1)))
    if balance is not None:
        return balance

    id = participant.id
    start_balance = get_end_of_year_balance(db, participant, year-1, current_year)
    delta = db.one("""
        SELECT (
                  SELECT COALESCE(sum(amount - (CASE WHEN (fee < 0) THEN fee ELSE 0 END)), 0) AS a
                    FROM exchanges
                   WHERE participant = %(id)s
                     AND extract(year from timestamp) = %(year)s
                     AND amount > 0
                     AND status = 'succeeded'
               ) + (
                  SELECT COALESCE(sum(amount - (CASE WHEN (fee > 0) THEN fee ELSE 0 END)), 0) AS a
                    FROM exchanges
                   WHERE participant = %(id)s
                     AND extract(year from timestamp) = %(year)s
                     AND amount < 0
                     AND status <> 'failed'
               ) + (
                  SELECT COALESCE(sum(-amount), 0) AS a
                    FROM transfers
                   WHERE tipper = %(id)s
                     AND extract(year from timestamp) = %(year)s
                     AND status = 'succeeded'
               ) + (
                  SELECT COALESCE(sum(amount), 0) AS a
                    FROM transfers
                   WHERE tippee = %(id)s
                     AND extract(year from timestamp) = %(year)s
                     AND status = 'succeeded'
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

    id = participant.id
    exchanges = db.all("""
        SELECT *
          FROM exchanges
         WHERE participant=%(id)s
           AND extract(year from timestamp) = %(year)s
    """, locals(), back_as=dict)
    transfers = db.all("""
        SELECT t.*, p.username, (SELECT username FROM participants WHERE id = team) AS team_name
          FROM transfers t
          JOIN participants p ON p.id = tipper
         WHERE t.tippee=%(id)s
           AND extract(year from t.timestamp) = %(year)s
        UNION ALL
        SELECT t.*, p.username, (SELECT username FROM participants WHERE id = team) AS team_name
          FROM transfers t
          JOIN participants p ON p.id = tippee
         WHERE t.tipper=%(id)s
           AND extract(year from t.timestamp) = %(year)s
    """, locals(), back_as=dict)

    if not (exchanges or transfers):
        return

    if transfers:
        yield dict(
            kind='totals',
            given=sum(t['amount'] for t in transfers if t['tipper'] == id and t['status'] == 'succeeded'),
            received=sum(
                t['amount'] for t in transfers
                if t['tippee'] == id and t['status'] == 'succeeded' and t['context'] != 'refund'
            ),
            npatrons=len(set(t['tipper'] for t in transfers if t['tipper'] != id)),
            ntippees=len(set(t['tippee'] for t in transfers if t['tippee'] != id)),
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
    day_events, day_open = None, None  # for pyflakes
    for event in events:

        event['balance'] = balance

        event_date = event['timestamp'].date()
        if event_date != prev_date:
            if prev_date:
                day_open['wallet_delta'] = day_open['balance'] - balance
                yield day_open
                for e in day_events:
                    yield e
                yield dict(kind='day-close', balance=balance)
            day_events = []
            day_open = dict(kind='day-open', date=event_date, balance=balance)
            if payday_dates:
                while payday_dates and payday_dates[-1] > event_date:
                    payday_dates.pop()
                payday_date = payday_dates[-1] if payday_dates else None
                if event_date == payday_date:
                    day_open['payday_number'] = len(payday_dates)
            prev_date = event_date

        if 'fee' in event:
            if event['amount'] > 0:
                kind = 'payout-refund' if event['refund_ref'] else 'charge'
                event['bank_delta'] = -event['amount'] - max(event['fee'], 0)
                event['wallet_delta'] = event['amount'] - min(event['fee'], 0)
                if event['status'] == 'succeeded':
                    balance -= event['wallet_delta']
            else:
                kind = 'payin-refund' if event['refund_ref'] else 'credit'
                event['bank_delta'] = -event['amount'] - min(event['fee'], 0)
                event['wallet_delta'] = event['amount'] - max(event['fee'], 0)
                if event['status'] != 'failed':
                    balance -= event['wallet_delta']
        else:
            kind = 'transfer'
            if event['tippee'] == id:
                event['wallet_delta'] = event['amount']
            else:
                event['wallet_delta'] = -event['amount']
            if event['status'] == 'succeeded':
                balance -= event['wallet_delta']
        event['kind'] = kind

        day_events.append(event)

    day_open['wallet_delta'] = day_open['balance'] - balance
    yield day_open
    for e in day_events:
        yield e
    yield dict(kind='day-close', balance=balance)


def export_history(participant, year, mode, key, back_as='namedtuple', require_key=False):
    db = participant.db
    base_url = website.canonical_url + '/~'
    params = dict(id=participant.id, year=year, base_url=base_url)
    out = {}
    if mode == 'aggregate':
        out['given'] = lambda: db.all("""
            SELECT (%(base_url)s || t.tippee::text) AS donee_url,
                   min(p.username) AS donee_username, sum(t.amount) AS amount
              FROM transfers t
              JOIN participants p ON p.id = t.tippee
             WHERE t.tipper = %(id)s
               AND extract(year from t.timestamp) = %(year)s
               AND t.status = 'succeeded'
               AND t.context <> 'refund'
          GROUP BY t.tippee
        """, params, back_as=back_as)
        out['taken'] = lambda: db.all("""
            SELECT (%(base_url)s || t.team::text) AS team_url,
                   min(p.username) AS team_username, sum(t.amount) AS amount
              FROM transfers t
              JOIN participants p ON p.id = t.team
             WHERE t.tippee = %(id)s
               AND t.context = 'take'
               AND extract(year from t.timestamp) = %(year)s
               AND t.status = 'succeeded'
          GROUP BY t.team
        """, params, back_as=back_as)
    else:
        out['exchanges'] = lambda: db.all("""
            SELECT timestamp, amount, fee, status, note
              FROM exchanges
             WHERE participant = %(id)s
               AND extract(year from timestamp) = %(year)s
          ORDER BY id ASC
        """, params, back_as=back_as)
        out['given'] = lambda: db.all("""
            SELECT timestamp, (%(base_url)s || t.tippee::text) AS donee_url,
                   p.username AS donee_username, t.amount, t.context
              FROM transfers t
              JOIN participants p ON p.id = t.tippee
             WHERE t.tipper = %(id)s
               AND extract(year from t.timestamp) = %(year)s
               AND t.status = 'succeeded'
          ORDER BY t.id ASC
        """, params, back_as=back_as)
        out['taken'] = lambda: db.all("""
            SELECT timestamp, (%(base_url)s || t.team::text) AS team_url,
                   p.username AS team_username, t.amount
              FROM transfers t
              JOIN participants p ON p.id = t.team
             WHERE t.tippee = %(id)s
               AND t.context = 'take'
               AND extract(year from t.timestamp) = %(year)s
               AND t.status = 'succeeded'
          ORDER BY t.id ASC
        """, params, back_as=back_as)
        out['received'] = lambda: db.all("""
            SELECT timestamp, amount, context
              FROM transfers
             WHERE tippee = %(id)s
               AND context <> 'take'
               AND extract(year from timestamp) = %(year)s
               AND status = 'succeeded'
          ORDER BY id ASC
        """, params, back_as=back_as)

    if key:
        try:
            return out[key]()
        except KeyError:
            raise Response(400, "bad key `%s`" % key)
    elif require_key:
        raise Response(400, "missing `key` parameter")
    else:
        return {k: v() for k, v in out.items()}
