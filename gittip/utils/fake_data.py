from faker import Factory
from gittip import wireup, MAX_TIP, MIN_TIP
from gittip.elsewhere import PLATFORMS
from gittip.models.participant import Participant

import datetime
import decimal
import random
import string


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


def fake_balance(max_amount=100):
    """Return a random amount between 0 and max_amount.
    """
    return random.random() * max_amount


def fake_int_id(nmax=2 ** 31 -1):
    """Create a random int id.
    """
    return random.randint(0, nmax)


def fake_sentence(start=1, stop=100):
    """Create a sentence of random length.
    """
    return faker.sentence(random.randrange(start,stop))


def fake_participant(db, number="singular", is_admin=False):
    """Create a fake User.
    """
    username = faker.first_name() + fake_text_id(3)
    _fake_thing( db
               , "participants"
               , id=fake_int_id()
               , username=username
               , username_lower=username.lower()
               , statement=fake_sentence()
               , ctime=faker.date_time_this_year()
               , is_admin=is_admin
               , balance=fake_balance()
               , anonymous_giving=(random.randrange(5) == 0)
               , anonymous_receiving=(random.randrange(5) == 0)
               , goal=fake_balance()
               , balanced_customer_href=faker.uri()
               , last_ach_result=''
               , is_suspicious=False
               , last_bill_result=''  # Needed to not be suspicious
               , claimed_time=faker.date_time_this_year()
               , number=number
                )
    #Call participant constructor to perform other DB initialization
    return Participant.from_username(username)



def fake_tip_amount():
    amount = ((decimal.Decimal(random.random()) * (MAX_TIP - MIN_TIP))
            + MIN_TIP)

    decimal_amount = decimal.Decimal(amount).quantize(decimal.Decimal('.01'))

    return decimal_amount


def fake_tip(db, tipper, tippee):
    """Create a fake tip.
    """
    return _fake_thing( db
               , "tips"
               , id=fake_int_id()
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
               , id=fake_int_id()
               , platform=platform
               , user_id=fake_text_id()
               , user_name=participant.username
               , is_locked=False
               , participant=participant.username
               , extra_info=None
                )


def fake_transfer(db, tipper, tippee):
        return _fake_thing( db
               , "transfers"
               , id=fake_int_id()
               , timestamp=faker.date_time_this_year()
               , tipper=tipper.username
               , tippee=tippee.username
               , amount=fake_tip_amount()
                )


def populate_db(db, num_participants=100, num_tips=200, num_teams=5, num_transfers=5000):
    """Populate DB with fake data.
    """
    #Make the participants
    participants = []
    for i in xrange(num_participants):
        participants.append(fake_participant(db))

    #Make the "Elsewhere's"
    for p in participants:
        #All participants get between 1 and 3 elsewheres
        num_elsewheres = random.randint(1, 3)
        for platform_name in random.sample(PLATFORMS, num_elsewheres):
            fake_elsewhere(db, p, platform_name)

    #Make teams
    for i in xrange(num_teams):
        t = fake_participant(db, number="plural")
        #Add 1 to 3 members to the team
        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            t.add_member(p)

    #Make the tips
    tips = []
    for i in xrange(num_tips):
        tipper, tippee = random.sample(participants, 2)
        tips.append(fake_tip(db, tipper, tippee))


    #Make the transfers
    transfers = []
    for i in xrange(num_transfers):
        tipper, tippee = random.sample(participants, 2)
        transfers.append(fake_transfer(db, tipper, tippee))


    #Make some paydays
    #First determine the boundaries - min and max date
    min_date = min(min(x['ctime'] for x in tips), \
                   min(x['timestamp'] for x in transfers))
    max_date = max(max(x['ctime'] for x in tips), \
                   max(x['timestamp'] for x in transfers))
    #iterate through min_date, max_date one week at a time
    date = min_date
    while date < max_date:
        end_date = date + datetime.timedelta(days=7)
        week_tips = filter(lambda x: date <= x['ctime'] <= end_date, tips)
        week_transfers = filter(lambda x: date <= x['timestamp'] <= end_date, transfers)
        week_participants = filter(lambda x: x.ctime.replace(tzinfo=None) <= end_date, participants)
        actives=set()
        tippers=set()
        for xfers in week_tips, week_transfers:
            actives.update(x['tipper'] for x in xfers)
            actives.update(x['tippee'] for x in xfers)
            tippers.update(x['tipper'] for x in xfers)
        payday = {
            'id': fake_int_id(),
            'ts_start': date,
            'ts_end': end_date,
            'ntips': len(week_tips),
            'ntransfers': len(week_transfers),
            'nparticipants': len(week_participants),
            'ntippers': len(tippers),
            'nactive': len(actives),
            'transfer_volume': sum(x['amount'] for x in week_transfers)
        }
        #Make ach_volume and charge_volume between 0 and 10% of transfer volume
        def rand_part():
            return decimal.Decimal(random.random()* 0.1)
        payday['ach_volume']   = -1 * payday['transfer_volume'] * rand_part()
        payday['charge_volume'] = payday['transfer_volume'] * rand_part()
        _fake_thing(db, "paydays", **payday)
        date = end_date



def main():
    populate_db(wireup.db(wireup.env()))

if __name__ == '__main__':
    main()
