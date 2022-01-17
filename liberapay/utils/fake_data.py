import datetime
from decimal import Decimal as D
import random
import string
import sys

from faker import Faker
from psycopg2 import IntegrityError

from liberapay.billing.transactions import (
    record_exchange_result, lock_bundles, _record_transfer_result
)
from liberapay.constants import D_CENT, DONATION_LIMITS, PERIOD_CONVERSION_RATES
from liberapay.exceptions import CommunityAlreadyExists
from liberapay.i18n.currencies import Money, MoneyBasket
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models import community


DONATION_PERIODS = tuple(PERIOD_CONVERSION_RATES.keys())


faker = Faker()


def _fake_thing(db, tablename, **kw):
    _cast = kw.pop('_cast', False)
    cols, vals = zip(*kw.items())
    cols = ', '.join(cols)
    placeholders = ', '.join(['%s']*len(vals))
    if _cast:
        tablename += ' AS r'
    returning = 'r' if _cast else '*'
    return db.one("""
        INSERT INTO {} ({}) VALUES ({}) RETURNING {}
    """.format(tablename, cols, placeholders, returning), vals)


def fake_text_id(size=6, chars=string.ascii_lowercase + string.digits):
    """Create a random text id.
    """
    return ''.join(random.choice(chars) for x in range(size))


def fake_sentence(start=1, stop=100):
    """Create a sentence of random length.
    """
    return faker.sentence(random.randrange(start, stop))


def fake_participant(db, kind=None):
    """Create a fake User.
    """
    username = faker.first_name() + fake_text_id(3)
    kind = kind or random.choice(('individual', 'organization'))
    is_a_person = kind in ('individual', 'organization')
    try:
        p = _fake_thing(
            db,
            "participants",
            username=username,
            email=username+'@example.org',
            balance=Money('0.00', 'EUR'),
            hide_giving=is_a_person and (random.randrange(5) == 0),
            hide_receiving=is_a_person and (random.randrange(5) == 0),
            status='active',
            join_time=faker.date_time_this_year(),
            kind=kind,
            mangopay_user_id=username,
            _cast=True,
        )
    except IntegrityError:
        return fake_participant(db)

    # Create wallet
    _fake_thing(
        db,
        "wallets",
        remote_id='-%i' % p.id,
        balance=p.balance,
        owner=p.id,
        remote_owner_id=p.mangopay_user_id,
    )

    return p


def fake_community(db, creator):
    """Create a fake community
    """
    name = community.normalize(faker.city())
    try:
        c = creator.create_community(name)
    except CommunityAlreadyExists:
        return fake_community(db, creator)
    creator.upsert_community_membership(True, c.id)
    return c


def random_money_amount(min_amount, max_amount):
    amount = D(random.random()) * (max_amount - min_amount) + min_amount
    return amount.quantize(D_CENT)


def fake_tip(db, tipper, tippee):
    """Create a fake tip.
    """
    period = random.choice(DONATION_PERIODS)
    limits = [l.amount for l in DONATION_LIMITS['EUR'][period]]
    periodic_amount = random_money_amount(*limits)
    amount = (periodic_amount * PERIOD_CONVERSION_RATES[period]).quantize(D_CENT)
    return _fake_thing(
        db,
        "tips",
        ctime=faker.date_time_this_year(),
        mtime=faker.date_time_this_month(),
        tipper=tipper.id,
        tippee=tippee.id,
        amount=Money(amount, 'EUR'),
        period=period,
        periodic_amount=Money(periodic_amount, 'EUR'),
        visibility=1,
    )


def fake_elsewhere(db, participant, platform):
    """Create a fake elsewhere.
    """
    _fake_thing(
        db,
        "elsewhere",
        platform=platform,
        user_id=fake_text_id(),
        user_name=participant.id,
        participant=participant.id,
        domain='',
    )


def fake_transfer(db, tipper, tippee, amount, timestamp):
    status = 'succeeded'
    t = _fake_thing(
        db,
        "transfers",
        timestamp=timestamp,
        tipper=tipper.id,
        tippee=tippee.id,
        amount=amount,
        context='tip',
        status='pre',
        wallet_from='-%s' % tipper.id,
        wallet_to='-%s' % tippee.id,
    )
    lock_bundles(db, t)
    _record_transfer_result(db, t.id, status)
    return t


def fake_exchange(db, participant, amount, fee, vat, timestamp):
    routes = ExchangeRoute.from_network(participant, 'mango-cc', currency='EUR')
    if routes:
        route = routes[0]
    else:
        route = _fake_thing(
            db,
            "exchange_routes",
            participant=participant.id,
            network='mango-cc',
            address='-1',
            status='chargeable',
            one_off=False,
            remote_user_id=participant.mangopay_user_id,
            currency='EUR',
        )
    e = _fake_thing(
        db,
        "exchanges",
        timestamp=timestamp,
        participant=participant.id,
        amount=amount,
        fee=fee,
        vat=vat,
        status='pre',
        route=route.id,
        wallet_id='-%i' % participant.id,
    )
    record_exchange_result(db, e.id, -e.id, 'succeeded', '', participant)
    return e


def populate_db(website, num_participants=100, num_tips=200, num_teams=5, num_transfers=5000, num_communities=20):
    """Populate DB with fake data.
    """
    db = website.db

    # Speed things up
    db.run("""
        DO $$ BEGIN
            EXECUTE 'ALTER DATABASE '||current_database()||' SET synchronous_commit TO off';
        END $$
    """)

    print("Making Participants")
    participants = []
    for i in range(num_participants):
        participants.append(fake_participant(db))

    print("Making Teams")
    teams = []
    for i in range(num_teams):
        team = fake_participant(db, kind="group")
        # Add 1 to 3 members to the team
        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            team.add_member(p)
        teams.append(team)
    participants.extend(teams)

    print("Making Elsewheres")
    platforms = [p.name for p in website.platforms]
    for p in participants:
        # All participants get between 0 and 3 elsewheres
        num_elsewheres = random.randint(0, 3)
        for platform_name in random.sample(platforms, num_elsewheres):
            fake_elsewhere(db, p, platform_name)

    print("Making Communities")
    for i in range(num_communities):
        creator = random.sample(participants, 1)
        community = fake_community(db, creator[0])

        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            p.upsert_community_membership(True, community.id)

    print("Making Tips")
    tips = []
    for i in range(num_tips):
        tipper, tippee = random.sample(participants, 2)
        tips.append(fake_tip(db, tipper, tippee))

    # Transfers
    min_amount, max_amount = [l.amount for l in DONATION_LIMITS['EUR']['weekly']]
    transfers = []
    for i in range(num_transfers):
        tipper, tippee = random.sample(participants, 2)
        while tipper.kind in ('group', 'community') or \
              tippee.kind in ('group', 'community'):
            tipper, tippee = random.sample(participants, 2)
        sys.stdout.write("\rMaking Transfers (%i/%i)" % (i+1, num_transfers))
        sys.stdout.flush()
        amount = Money(random_money_amount(min_amount, max_amount), 'EUR')
        zero = amount.zero()
        ts = faker.date_time_this_year()
        fake_exchange(db, tipper, amount, zero, zero, (ts - datetime.timedelta(days=1)))
        transfers.append(fake_transfer(db, tipper, tippee, amount, ts))
    print("")

    # Paydays
    # First determine the boundaries - min and max date
    min_date = min(min(x.ctime for x in tips),
                   min(x.timestamp for x in transfers))
    max_date = max(max(x.ctime for x in tips),
                   max(x.timestamp for x in transfers))
    # iterate through min_date, max_date one week at a time
    payday_counter = 1
    date = min_date
    paydays_total = (max_date - min_date).days/7 + 1
    while date < max_date:
        sys.stdout.write("\rMaking Paydays (%i/%i)" % (payday_counter, paydays_total))
        sys.stdout.flush()
        payday_counter += 1
        end_date = date + datetime.timedelta(days=7)
        week_tips = [x for x in tips if date < x.ctime < end_date]
        week_transfers = [x for x in transfers if date < x.timestamp < end_date]
        week_participants = [x for x in participants if x.join_time < end_date]
        actives = set()
        tippers = set()
        for xfers in week_tips, week_transfers:
            actives.update(x.tipper for x in xfers)
            actives.update(x.tippee for x in xfers)
            tippers.update(x.tipper for x in xfers)
        payday = {
            'ts_start': date,
            'ts_end': end_date,
            'ntips': len(week_tips),
            'ntransfers': len(week_transfers),
            'nparticipants': len(week_participants),
            'ntippers': len(tippers),
            'nactive': len(actives),
            'transfer_volume': MoneyBasket(x.amount for x in week_transfers),
            'public_log': '',
        }
        _fake_thing(db, "paydays", **payday)
        date = end_date
    print("")


def main():
    from liberapay.main import website
    populate_db(website)
    website.db.self_check()


if __name__ == '__main__':
    main()
