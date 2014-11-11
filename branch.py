"""Helper script for pr#2917. Should be pruned from master.

This spits out UPDATE SQL lines, one for each Bitbucket account we want to
update. Redirect it into an update.sql file on the 2917 branch. The branch.sql
references update.sql.

The input should be a list of `is_team\tusername`. You can generate this with a
SQL script like this:

    copy (select is_team, user_name from elsewhere where platform='bitbucket')
    to stdout;

Run that like:

    psql < bitbucket.sql > bitbucket.txt

Then you're ready to run this present script:

    [gratipay]$ python branch.py < bitbucket.txt > update.sql

We're keeping update.sql in git, to be pruned from master once 2917 lands.

"""
import requests, sys

for line in sys.stdin:
    is_team, username = line.strip().split()
    endpoint, other = ('users', 'teams') if is_team == 'f' else ('teams', 'users')


    # Try to fetch a record from the Bitbucket API. Manually retry as a
    # team if trying as a user fails, and vice versa.

    r = requests.get('https://bitbucket.org/api/2.0/' + endpoint + '/' + username)
    if r.status_code == 404:
        r = requests.get('https://bitbucket.org/api/2.0/' + other + '/' + username)
        if r.status_code == 200:
            is_team = 't' if is_team == 'f' else 'f'
            print >> sys.stderr, username, "has gone from", endpoint, "to", other


    # Spit out a line of SQL to make the update we want.

    if r.status_code == 200:
        print "UPDATE elsewhere SET user_id='{}', is_team='{}' " \
              "WHERE platform='bitbucket' and user_name='{}';" \
              .format(r.json()['uuid'], is_team, username)
        sys.stdout.flush()


    # Note genuine 404s to stderr.

    else:
        print >> sys.stderr, r.status_code, username, r.text
