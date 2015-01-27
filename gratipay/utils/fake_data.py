import datetime
from decimal import Decimal as D
import random
import string
import sys

from faker import Factory
from psycopg2 import IntegrityError

from gratipay import wireup, MAX_TIP_SINGULAR, MIN_TIP
from gratipay.elsewhere import PLATFORMS
from gratipay.models.participant import Participant
from gratipay.models import community
from gratipay.models import check_db

faker = Factory.create()

def _fake_thing(db, tablename, **kw):
    column_names = []
    column_value_placeholders = []
    column_values = []

    for k,v in kw.items():
        column_names.append(k)
        column_value_placeholders.append("%s")
        column_values.append(v)

    column_names = ", ".join(column_names)
    column_value_placeholders = ", ".join(column_value_placeholders)

    db.run( "INSERT INTO {} ({}) VALUES ({})"
            .format(tablename, column_names, column_value_placeholders)
          , column_values
           )
    return kw


def fake_text_id(size=6, chars=string.ascii_lowercase + string.digits):
    """Create a random text id.
    """
    return ''.join(random.choice(chars) for x in range(size))


def fake_sentence(start=1, stop=100):
    """Create a sentence of random length.
    """
    return faker.sentence(random.randrange(start,stop))


def fake_participant(db, number="singular", is_admin=False):
    """Create a fake User.
    """
    username = faker.first_name() + fake_text_id(3)
    try:
        _fake_thing( db
                   , "participants"
                   , username=username
                   , username_lower=username.lower()
                   , ctime=faker.date_time_this_year()
                   , is_admin=is_admin
                   , balance=0
                   , anonymous_giving=(random.randrange(5) == 0)
                   , anonymous_receiving=(number != 'plural' and random.randrange(5) == 0)
                   , balanced_customer_href=faker.uri()
                   , last_ach_result=''
                   , is_suspicious=False
                   , last_bill_result=''  # Needed to not be suspicious
                   , claimed_time=faker.date_time_this_year()
                   , number=number
                    )
    except IntegrityError:
      return fake_participant(db, number, is_admin)

    #Call participant constructor to perform other DB initialization
    return Participant.from_username(username)


def fake_community(db, creator):
    """Create a fake community
    """
    name = faker.city()
    if not community.name_pattern.match(name):
        return fake_community(db, creator)

    slug = community.slugize(name)

    creator.insert_into_communities(True, name, slug)

    return community.Community.from_slug(slug)


def fake_tip_amount():
    amount = ((D(random.random()) * (MAX_TIP_SINGULAR - MIN_TIP))
            + MIN_TIP)

    decimal_amount = D(amount).quantize(D('.01'))
    while decimal_amount == D('0.00'):
        # https://github.com/gratipay/gratipay.com/issues/2950
        decimal_amount = fake_tip_amount()
    return decimal_amount


def fake_tip(db, tipper, tippee):
    """Create a fake tip.
    """
    return _fake_thing( db
                      , "tips"
                      , ctime=faker.date_time_this_year()
                      , mtime=faker.date_time_this_month()
                      , tipper=tipper.username
                      , tippee=tippee.username
                      , amount=fake_tip_amount()
                       )


def fake_elsewhere(db, participant, platform):
    """Create a fake elsewhere.
    """
    _fake_thing( db
               , "elsewhere"
               , platform=platform
               , user_id=fake_text_id()
               , user_name=participant.username
               , participant=participant.username
               , extra_info=None
                )


def fake_transfer(db, tipper, tippee):
    return _fake_thing( db
           , "transfers"
           , timestamp=faker.date_time_this_year()
           , tipper=tipper.username
           , tippee=tippee.username
           , amount=fake_tip_amount()
           , context='tip'
            )

def fake_exchange(db, participant, amount, fee, timestamp):
    return _fake_thing( db
                      , "exchanges"
                      , timestamp=timestamp
                      , participant=participant.username
                      , amount=amount
                      , fee=fee
                      , status='succeeded'
                       )

def prep_db(db):
    db.run("""
        CREATE OR REPLACE FUNCTION process_transfer() RETURNS trigger AS $$
            BEGIN
                UPDATE participants
                   SET balance = balance + NEW.amount
                 WHERE username = NEW.tippee;

                UPDATE participants
                   SET balance = balance - NEW.amount
                 WHERE username = NEW.tipper;

                RETURN NULL;
            END;
        $$ language plpgsql;

        CREATE TRIGGER process_transfer AFTER INSERT ON transfers
            FOR EACH ROW EXECUTE PROCEDURE process_transfer();

        CREATE OR REPLACE FUNCTION process_exchange() RETURNS trigger AS $$
            BEGIN
                IF NEW.amount > 0 THEN
                    UPDATE participants
                       SET balance = balance + NEW.amount
                     WHERE username = NEW.participant;
                ELSE
                    UPDATE participants
                       SET balance = balance + NEW.amount - NEW.fee
                     WHERE username = NEW.participant;
                END IF;

                RETURN NULL;
            END;
        $$ language plpgsql;

        CREATE TRIGGER process_exchange AFTER INSERT ON exchanges
            FOR EACH ROW EXECUTE PROCEDURE process_exchange();

        CREATE OR REPLACE FUNCTION process_payday() RETURNS trigger AS $$
            BEGIN
                SELECT COALESCE(SUM(amount+fee), 0)
                  FROM exchanges
                 WHERE timestamp > NEW.ts_start
                   AND timestamp < NEW.ts_end
                   AND amount > 0
                  INTO NEW.charge_volume;

                SELECT COALESCE(SUM(fee), 0)
                  FROM exchanges
                 WHERE timestamp > NEW.ts_start
                   AND timestamp < NEW.ts_end
                   AND amount > 0
                  INTO NEW.charge_fees_volume;

                SELECT COALESCE(SUM(amount), 0)
                  FROM exchanges
                 WHERE timestamp > NEW.ts_start
                   AND timestamp < NEW.ts_end
                   AND amount < 0
                  INTO NEW.ach_volume;

                SELECT COALESCE(SUM(fee), 0)
                  FROM exchanges
                 WHERE timestamp > NEW.ts_start
                   AND timestamp < NEW.ts_end
                   AND amount < 0
                  INTO NEW.ach_fees_volume;

                RETURN NEW;
            END;
        $$ language plpgsql;

        CREATE TRIGGER process_payday BEFORE INSERT ON paydays
            FOR EACH ROW EXECUTE PROCEDURE process_payday();
    """)

def clean_db(db):
    db.run("""
        DROP FUNCTION process_transfer() CASCADE;
        DROP FUNCTION process_exchange() CASCADE;
        DROP FUNCTION process_payday() CASCADE;
    """)


def populate_db(db, num_participants=100, num_tips=200, num_teams=5, num_transfers=5000, num_communities=20):
    """Populate DB with fake data.
    """
    print("Making Participants")
    participants = []
    for i in xrange(num_participants):
        participants.append(fake_participant(db))

    print("Making Teams")
    for i in xrange(num_teams):
        team = fake_participant(db, number="plural")
        #Add 1 to 3 members to the team
        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            team.add_member(p)
        participants.append(team)

    print("Making Elsewheres")
    for p in participants:
        #All participants get between 1 and 3 elsewheres
        num_elsewheres = random.randint(1, 3)
        for platform_name in random.sample(PLATFORMS, num_elsewheres):
            fake_elsewhere(db, p, platform_name)

    print("Making Communities")
    for i in xrange(num_communities):
        creator = random.sample(participants, 1)
        community = fake_community(db, creator[0])

        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            p.insert_into_communities(True, community.name, community.slug)

    print("Making Tips")
    tips = []
    for i in xrange(num_tips):
        tipper, tippee = random.sample(participants, 2)
        tips.append(fake_tip(db, tipper, tippee))

    # Transfers
    transfers = []
    for i in xrange(num_transfers):
        sys.stdout.write("\rMaking Transfers (%i/%i)" % (i+1, num_transfers))
        sys.stdout.flush()
        tipper, tippee = random.sample(participants, 2)
        transfers.append(fake_transfer(db, tipper, tippee))
    print("")

    # Paydays
    # First determine the boundaries - min and max date
    min_date = min(min(x['ctime'] for x in tips), \
                   min(x['timestamp'] for x in transfers))
    max_date = max(max(x['ctime'] for x in tips), \
                   max(x['timestamp'] for x in transfers))
    # iterate through min_date, max_date one week at a time
    payday_counter = 1
    date = min_date
    paydays_total = (max_date - min_date).days/7 + 1
    while date < max_date:
        sys.stdout.write("\rMaking Paydays (%i/%i)" % (payday_counter, paydays_total))
        sys.stdout.flush()
        payday_counter += 1
        end_date = date + datetime.timedelta(days=7)
        week_tips = filter(lambda x: date < x['ctime'] < end_date, tips)
        week_transfers = filter(lambda x: date < x['timestamp'] < end_date, transfers)
        week_participants = filter(lambda x: x.ctime.replace(tzinfo=None) < end_date, participants)
        for p in week_participants:
            transfers_in = filter(lambda x: x['tippee'] == p.username, week_transfers)
            transfers_out = filter(lambda x: x['tipper'] == p.username, week_transfers)
            amount_in = sum([t['amount'] for t in transfers_in])
            amount_out = sum([t['amount'] for t in transfers_out])
            amount = amount_out - amount_in
            if amount != 0:
                fee = amount * D('0.02')
                fee = abs(fee.quantize(D('.01')))
                fake_exchange(
                    db=db,
                    participant=p,
                    amount=amount,
                    fee=fee,
                    timestamp=(end_date - datetime.timedelta(seconds=1))
                )
        actives=set()
        tippers=set()
        for xfers in week_tips, week_transfers:
            actives.update(x['tipper'] for x in xfers)
            actives.update(x['tippee'] for x in xfers)
            tippers.update(x['tipper'] for x in xfers)
        payday = {
            'ts_start': date,
            'ts_end': end_date,
            'ntips': len(week_tips),
            'ntransfers': len(week_transfers),
            'nparticipants': len(week_participants),
            'ntippers': len(tippers),
            'nactive': len(actives),
            'transfer_volume': sum(x['amount'] for x in week_transfers)
        }
        _fake_thing(db, "paydays", **payday)
        date = end_date
    print("")

def main():
    db = wireup.db(wireup.env())
    prep_db(db)
    populate_db(db)
    clean_db(db)
    check_db(db)


if __name__ == '__main__':
    main()
