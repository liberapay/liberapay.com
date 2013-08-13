from faker import Factory
from gittip import orm, wireup, MAX_TIP, MIN_TIP
from gittip.models.tip import Tip
from gittip.models.participant import Participant
from gittip.models.elsewhere import Elsewhere

import gittip
import decimal
import random
import string

faker = Factory.create()

platforms = ['github', 'twitter', 'bitbucket']


def fake_text_id(size=6, chars=string.ascii_lowercase + string.digits):
    """
    Create a random text id
    """
    return ''.join(random.choice(chars) for x in range(size))


def fake_balance(max_amount=100):
    """
    Return a random amount between 0 and max_amount
    """
    return random.random() * max_amount

def fake_int_id(nmax=2 ** 31 -1):
    """
    Create a random int id
    """
    return random.randint(0, nmax)


def fake_participant(is_admin=False, anonymous=False):
    """
    Create a fake User
    """
    username = faker.firstName() + fake_text_id(3)
    return Participant(
        id=fake_int_id(),
        username=username,
        username_lower=username.lower(),
        statement=faker.sentence(),
        ctime=faker.dateTimeThisYear(),
        is_admin=is_admin,
        balance=fake_balance(),
        anonymous=anonymous,
        goal=fake_balance(),
        balanced_account_uri=faker.uri(),
        last_ach_result='',
        is_suspicious=False,
        last_bill_result='',  # Needed to not be suspicious
        claimed_time=faker.dateTimeThisYear(),
        number="singular"
    )

def fake_tip_amount():
    amount = ((decimal.Decimal(random.random()) * (MAX_TIP - MIN_TIP))
            + MIN_TIP)
    
    decimal_amount = decimal.Decimal(amount).quantize(decimal.Decimal('.01'))

    return decimal_amount


def fake_tip(tipper, tippee):
    """
    Create a fake tip
    """
    return Tip(
        id=fake_int_id(),
        ctime=faker.dateTimeThisYear(),
        mtime=faker.dateTimeThisMonth(),
        tipper=tipper.username,
        tippee=tippee.username,
        amount=fake_tip_amount()
    )


def fake_elsewhere(participant, platform=None):
    """
    Create a fake elsewhere
    """
    if platform is None:
        platform = random.choice(platforms)

    info_templates = {
        "github": {
            "name": participant.username,
            "html_url": "https://github.com/" + participant.username,
            "type": "User",
            "login": participant.username
        },
        "twitter": {
            "name": participant.username,
            "html_url": "https://twitter.com/" + participant.username,
            "screen_name": participant.username
        },
        "bitbucket": {
            "display_name": participant.username,
            "username": participant.username,
            "is_team": "False",
            "html_url": "https://bitbucket.org/" + participant.username,
        }
    }

    return Elsewhere(
        id=fake_int_id(),
        platform=platform,
        user_id=fake_text_id(),
        is_locked=False,
        participant=participant.username,
        user_info=info_templates[platform]
    )


def populate_db(session, num_participants=100, num_tips=50, num_teams=5):
    """
    Populate DB with fake data
    """
    #Make the participants
    participants = []
    for i in xrange(num_participants):
        p = fake_participant()
        session.add(p)
        participants.append(p)

    #Make the "Elsewhere's"
    for p in participants:
        #All participants get between 1 and 3 elsewheres
        num_elsewheres = random.randint(1, 3)
        for platform_name in platforms[:num_elsewheres]:
            e = fake_elsewhere(p, platform_name)
            session.add(e)

    #Make teams
    teams = []
    for i in xrange(num_teams):
        t = fake_participant()
        t.number = "plural"
        session.add(t)
        session.commit()
        #Add 1 to 3 members to the team
        members = random.sample(participants, random.randint(1, 3))
        for p in members:
            t.add_member(p)
        teams.append(t)

    #Make the tips
    tips = []
    for i in xrange(num_tips):
        tipper, tippee = random.sample(participants, 2)
        t = fake_tip(tipper, tippee)
        tips.append(t)
        session.add(t)
    session.commit()


def main():
    db = orm.db
    dbsession = db.session
    gittip.db = wireup.db()
    populate_db(dbsession)

if __name__ == '__main__':
    main()
