import datetime
from decimal import Decimal as D
import random
import string
import sys

from faker import Factory
from psycopg2 import IntegrityError

from liberapay import wireup
from liberapay.billing.exchanges import record_exchange_result, _record_transfer_result
from liberapay.constants import MAX_TIP, MIN_TIP
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.models import community
from liberapay.models import check_db
from liberapay.wireup import accounts_elsewhere, env


faker = Factory.create()


def _fake_thing(db, tablename, **kw):
    cols, vals = zip(*kw.items())
    cols = ', '.join(cols)
    placeholders = ', '.join(['%s']*len(vals))
    return db.one("""
        INSERT INTO {} ({}) VALUES ({}) RETURNING *
    """.format(tablename, cols, placeholders), vals)


def fake_text_id(size=6, chars=string.ascii_lowercase + string.digits):
    """Create a random text id.
    """
    return ''.join(random.choice(chars) for x in range(size))


def fake_sentence(start=1, stop=100):
    """Create a sentence of random length.
    """
    return faker.sentence(random.randrange(start,stop))


def fake_participant(db, kind=None, is_admin=False):
    """Create a fake User.
    """
    username = faker.first_name() + fake_text_id(3)
    kind = kind or random.choice(('individual', 'organization'))
    is_a_person = kind in ('individual', 'organization')
    try:
        _fake_thing( db
                   , "participants"
                   , username=username
                   , password=None if not is_a_person else 'x'
                   , email=username+'@example.org'
                   , is_admin=is_admin
                   , balance=0
                   , hide_giving=is_a_person and (random.randrange(5) == 0)
                   , hide_receiving=is_a_person and (random.randrange(5) == 0)
                   , is_suspicious=False
                   , status='active'
                   , join_time=faker.date_time_this_year()
                   , kind=kind
                   , mangopay_user_id=username
                   , mangopay_wallet_id='-1'
                    )
    except IntegrityError:
        return fake_participant(db, is_admin)

    #Call participant constructor to perform other DB initialization
    return Participant.from_username(username)


def fake_community(db, creator):
    """Create a fake community
    """
    name = community.normalize(faker.city())
    c = creator.create_community(name)
    creator.update_community_status('memberships', True, c.id)
    return c


def fake_tip_amount():
    amount = (D(random.random()) * (MAX_TIP - MIN_TIP) + MIN_TIP)

    decimal_amount = D(amount).quantize(D('.01'))
    while decimal_amount == D('0.00'):
        # https://github.com/gratipay/gratipay.com/issues/2950
        decimal_amount = fake_tip_amount()
    return decimal_amount


def fake_tip(db, tipper, tippee):
    """Create a fake tip.
    """
    return _fake_thing(
        db,
        "tips",
        ctime=faker.date_time_this_year(),
        mtime=faker.date_time_this_month(),
        tipper=tipper.id,
        tippee=tippee.id,
        amount=fake_tip_amount(),
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
        extra_info=None,
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
        status=status,
    )
    _record_transfer_result(db, t.id, status)
    return t


def fake_exchange(db, participant, amount, fee, timestamp):
    route = ExchangeRoute.from_network(participant, 'mango-cc')
    if not route:
        route = _fake_thing(
            db,
            "exchange_routes",
            participant=participant.id,
            network='mango-cc',
            address='-1',
            error='',
            one_off=False,
        )
    e = _fake_thing(
        db,
        "exchanges",
        timestamp=timestamp,
        participant=participant.id,
        amount=amount,
        fee=fee,
        status='pre',
        route=route.id,
    )
    record_exchange_result(db, e.id, 'succeeded', '', participant)
    return e


def populate_db(db, num_participants=100, num_tips=200, num_teams=5, num_transfers=5000, num_communities=20):
    """Populate DB with fake data.
    """
    print("Making Participants")
    participants = []
    for i in range(num_participants):
        participants.append(fake_participant(db))

    print("Making Teams")
    teams = []
    for i in range(num_teams):
        team = fake_participant(db, kind="group")
        #Add 1 to 3 members to the team
        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            team.add_member(p)
        teams.append(team)
    participants.extend(teams)

    print("Making Elsewheres")
    e = env()
    class Website(object):
        def asset(self, *a):
            return ''
    website = Website()
    accounts_elsewhere(website, e)
    platforms = [p.name for p in website.platforms]
    for p in participants:
        #All participants get between 0 and 3 elsewheres
        num_elsewheres = random.randint(0, 3)
        for platform_name in random.sample(platforms, num_elsewheres):
            fake_elsewhere(db, p, platform_name)

    print("Making Communities")
    for i in range(num_communities):
        creator = random.sample(participants, 1)
        community = fake_community(db, creator[0])

        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            p.update_community_status('memberships', True, community.id)

    print("Making Tips")
    tips = []
    for i in range(num_tips):
        tipper, tippee = random.sample(participants, 2)
        tips.append(fake_tip(db, tipper, tippee))

    # Transfers
    transfers = []
    for i in range(num_transfers):
        tipper, tippee = random.sample(participants, 2)
        while tipper.kind in ('group', 'community') or \
              tippee.kind in ('group', 'community'):
            tipper, tippee = random.sample(participants, 2)
        sys.stdout.write("\rMaking Transfers (%i/%i)" % (i+1, num_transfers))
        sys.stdout.flush()
        amount = fake_tip_amount()
        ts = faker.date_time_this_year()
        fake_exchange(db, tipper, amount, 0, (ts - datetime.timedelta(days=1)))
        transfers.append(fake_transfer(db, tipper, tippee, amount, ts))
    print("")

    # Paydays
    # First determine the boundaries - min and max date
    min_date = min(min(x.ctime for x in tips), \
                   min(x.timestamp for x in transfers))
    max_date = max(max(x.ctime for x in tips), \
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
        actives=set()
        tippers=set()
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
            'transfer_volume': sum(x.amount for x in week_transfers)
        }
        _fake_thing(db, "paydays", **payday)
        date = end_date
    print("")


def main():
    db = wireup.db(wireup.env())
    populate_db(db)
    check_db(db)


if __name__ == '__main__':
    main()
