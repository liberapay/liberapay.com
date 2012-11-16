This is Gittip, a sustainable crowd-funding platform.

The basis of Gittip is an anonymous gift between $1 and $24 per week to people
who do great work. These gifts come with no explicit strings attached.

The Gittip gift exchange happens every Thursday. On Thursday, we charge
people's credit cards and the money goes into a marketplace account with
[Balanced Payments](https://www.balancedpayments.com). Money is allocated to
other participants, and for those with a bank account attached and money due,
the money is deposited in their bank account on Friday.

Gittip is funded on Gittip.


Installation
============

The site is built with [Python](http://www.python.org/) 2.7 and the
[Aspen](http://aspen.io/) web framework, and is hosted on
[Heroku](http://www.heroku.com/).
[Balanced](https://www.balancedpayments.com/) is used for credit card
processing, and Google for analytics.

You need python2.7 on your PATH.

You need [Postgres](http://www.postgresql.org/) with headers installed.

Once you have Python and Postgres, you can use make to build and launch Gittip:

    $ make run

If you don't have make, look at the Makefile to see what steps you need to
perform to build and launch Gittip. The Makefile is pretty simple and
straightforward. 

All Python dependencies (including virtualenv) are bundled with Gittip in the
vendor/ directory. Gittip is designed so that you don't manage its virtualenv
directly and you don't download its dependencies at build time.


local.env
=========

When using `make run`, Gittip's execution environment is defined in a
`local.env` file, which is not included in the source code repo. If you `make
run` you'll have one generated for you, which you can then tweak as needed.
Here's the default:

    CANONICAL_HOST=localhost:8537
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

You probably don't need it, but at one point I had to set this to get psycopg2
working on Mac OS with EnterpriseDB's Postgres 9.1 installer:

    DYLD_LIBRARY_PATH=/Library/PostgreSQL/9.1/lib


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
suite is designed for the nosetests test runner (maybe it also works with
py.test?), and uses module-level test functions, with a context manager for
managing testing state. Please don't use test classes. As a rule of thumb, each
test case should perform one assertion. For a guided intro to Gittip's test
suite, check out tests/test_suite_intro.py.

Assuming you have make, the easiest way to run the test suite is:

    $ make test

However, the test suite deletes data in all tables in the public schema of the
database configured in your testing environment, and as a safety precaution, we
require the following key and value to be set in said environment:

    YES_PLEASE_DELETE_ALL_MY_DATA_VERY_OFTEN=Pretty please, with sugar on top.

`make test` will not set this for you. Run `make tests/env` and then edit that
file and manually add that key=value, then `make test` will work. Even just
importing the gittip.testing module will trigger deletion of all data. Without
this safety precaution, an attacker could try sneaking `import gittip.testing`
into a commit. Once their changeset was deployed, we would have ...  problems.
Of course, they could also remove the check in the same or even a different
commit. Of course, they could also sneak in whatever the heck code they wanted
to try to sneak in.

To invoke nosetests directly you should use the `swaddle` utility that comes
with Aspen. First `make tests/env`, edit it as noted above, and then:

    [gittip] $ cd tests/
    [gittip] $ swaddle env ../env/bin/nosetests



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
 - http://anyfu.com/ (also: http://ohours.org/)
 - http://videovivoapp.com/
 - http://techcrunch.com/2009/08/20/tipjoy-heads-to-the-deadpool/
 - http://hopemob.org/
 - http://www.awesomefoundation.org/
 - http://www.crowdrise.com/
 - http://www.chipin.com/
 - http://www.fundable.com/
 - https://www.modestneeds.org/
 - http://www.freedomsponsors.org/
 - https://gumroad.com/
 - http://macheist.com/
 - http://www.prosper.com/
 - http://togather.me/
