from decimal import Decimal as D
import random
import string

from faker import Faker
from psycopg2 import IntegrityError

from liberapay.constants import DONATION_LIMITS, PERIOD_CONVERSION_RATES
from liberapay.exceptions import CommunityAlreadyExists
from liberapay.i18n.currencies import D_CENT, Money
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
        return _fake_thing(
            db,
            "participants",
            username=username,
            email=username+'@example.org',
            hide_giving=is_a_person and (random.randrange(5) == 0),
            hide_receiving=is_a_person and (random.randrange(5) == 0),
            status='active',
            join_time=faker.date_time_this_year(),
            kind=kind,
            _cast=True,
        )
    except IntegrityError:
        return fake_participant(db)


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


def populate_db(website, num_participants=100, num_tips=200, num_teams=5, num_communities=20):
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


def main():
    from liberapay.main import website
    populate_db(website)
    website.db.self_check()


if __name__ == '__main__':
    main()
