This is Gittip, a platform for personal funding.

Gittip is a cooperative escrow agent for recurring micro-gifts, or gift tips.
Possible tip amounts per week are 0.00, 1.00, 3.00, 6.00, 12.00, and 24.00.

Friday is payday. On Friday, we charge people's credit cards and the money goes
into Gittip's (Zeta Design & Development, LLC's) bank account. Money is
allocated to other participants according to tips. Participants may withdraw
money at any time, though this is currently quite manual.


Installation
============

The site is built with Python 2.7 and the Aspen web framework, and is hosted on
Heroku. Balanced is used for credit card processing, and Google for analytics.

You need python2.7 on your PATH.

You need Postgres with headers installed. There's a simple Makefile for
building the software. All Python dependencies are included in vendor/. To
`make run` you need a local.env file in the distribution root with these keys:

    CANONICAL_HOST=
    CANONICAL_SCHEME=http
    DATABASE_URL=postgres://gittip@localhost/gittip
    STRIPE_SECRET_API_KEY=1
    STRIPE_PUBLISHABLE_API_KEY=1
    BALANCED_API_SECRET=90bb3648ca0a11e1a977026ba7e239a9
    GITHUB_CLIENT_ID=3785a9ac30df99feeef5
    GITHUB_CLIENT_SECRET=e69825fafa163a0b0b6d2424c107a49333d46985
    GITHUB_CALLBACK=http://localhost:8537/on/github/associate
    TWITTER_CONSUMER_KEY=QBB9vEhxO4DFiieRF68zTA
    TWITTER_CONSUMER_SECRET=mUymh1hVMiQdMQbduQFYRi79EYYVeOZGrhj27H59H78
    TWITTER_CALLBACK=http://127.0.0.1:8537/on/twitter/associate
    DYLD_LIBRARY_PATH=/Library/PostgreSQL/9.1/lib

The `BALANCED_API_SECRET` is a test marketplace. To generate a new secret for
your own testing run this command:

    curl -X POST https://api.balancedpayments.com/v1/api_keys | grep secret

Grab that secret and also create a new marketplace to test against:

    curl -X POST https://api.balancedpayments.com/v1/marketplaces -u <your_secret>:

The site works without this, except for the credit card page. Visit the
[Balanced Documentation](https://www.balancedpayments.com/docs) if you want to
know more about creating marketplaces.

The GITHUB_* keys are for a gittip-dev application in the Gittip organization
on Github. It points back to localhost:8537, which is where Gittip will be
running if you start it locally with `make run`. Similarly with the TWITTER_*
keys, but there they required us to spell it `127.0.0.1`.

The DYLD_LIBRARY_PATH thing is to get psycopg2 working on Mac OS with
EnterpriseDB's Postgres 9.1 installer. You might not need it.


Setting up the Database
-----------------------

Install PostgreSQL. The best version to use is 9.1, because Gittip uses the
hstore extension for unstructured data, and that isn't bundled with earlier
versions. If you're on a Mac, maybe try out Heroku's Postgres.app:

    http://postgresapp.com/

Add a "role" (Postgres user) that matches your OS username. Make sure it's a
superuser role and has login privileges. Here's a sample invocation of the
createuser executable that comes with Postgres that will do this for you,
assuming that a "postgres" superuser was already created as part of initial
installation:

    $ createuser --username postgres --superuser $USER 

It's also convenient to set the authentication method to "trust" in pg_hba.conf
for local connections, so you don't have to enter a password all the time.
Reload Postgres using pg_ctl for this to take effect.

Once Postgres is set up, run:

    $ ./makedb.sh

That will create a new gittip superuser and a gittip database (with UTC as the
default timezone), populated with structure from ./schema.sql. To change the
name of the database and/or user, pass them on the command line:

    $ ./makedb.sh mygittip myuser

If you only pass one argument it will be used for both dbname and owner role:

    $ ./makedb.sh gittip-test

The schema for the Gittip.com database is defined in schema.sql. It should be
considered append-only. The idea is that this is the log of DDL that we've run
against the production database. You should never change commands that have
already been run. New DDL will be (manually) run against the production
database as part of deployment.


Testing [![Testing](https://secure.travis-ci.org/whit537/www.gittip.com.png)](http://travis-ci.org/whit537/www.gittip.com)
-------

Please write unit tests for all new code and all code you change. Gittip's test
suite is designed for the nosetests test runner. Assuming you have make, the
easiest way to run the test suite is:

    $ make test

To invoke nosetests directly you need to set DATABASE_URL in its environment,
like so:

    [gittip] $ DATABASE_URL=postgres://gittip@localhost/gittip nosetests


See Also
========

 - http://www.kickstarter.com/
 - http://flattr.com/
 - http://tiptheweb.org/
 - http://www.indiegogo.com/
 - http://www.pledgemusic.com/
 - https://propster.me/
 - http://kachingle.com/
 - https://venmo.com/
 - https://www.snoball.com/
 - http://pledgie.com/
 - http://www.humblebundle.com/
 - https://www.crowdtilt.com/
 - http://www1.networkforgood.org/
 - http://anyfu.com/
 - http://videovivoapp.com/
 - http://techcrunch.com/2009/08/20/tipjoy-heads-to-the-deadpool/
 - http://hopemob.org/
 - http://www.awesomefoundation.org/
 - http://www.crowdrise.com/
 - http://www.chipin.com/
