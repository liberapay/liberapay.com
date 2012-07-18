This is Gittip, a platform for personal funding.

Gittip is a cooperative escrow agent for recurring micro-gifts, or gift tips.
Possible tip amounts per week are 0.00, 0.25, 3.00, 6.00, 12.00, and 24.00.

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
    DATABASE_URL=postgres://user:pass@localhost/dbname
    BALANCED_API_SECRET=90bb3648ca0a11e1a977026ba7e239a9
    GITHUB_CLIENT_ID=3785a9ac30df99feeef5
    GITHUB_CLIENT_SECRET=e69825fafa163a0b0b6d2424c107a49333d46985
    GITHUB_CALLBACK=http://localhost:8537/github/associate
    DYLD_LIBRARY_PATH=/Library/PostgreSQL/9.1/lib

The `BALANCED_API_SECRET` is a test marketplace. To generate a new secret for
your own testing run this command:

    curl -X POST https://api.balancedpayments.com/v1/api_keys | grep secret

Grab that secret and also create a new marketplace to test against:

    curl -X POST https://api.balancedpayments.com/v1/marketplaces -u <your_secret>:

The site works without this, except for the credit card page (you have to set
this). Visit the [Balanced Documentation](https://www.balancedpayments.com/docs)
if you want to know more about creating marketplace's.

The GITHUB_* keys are for a gittip-dev application in the Gittip organization
on Github. It points back to localhost:8537, which is where Gittip will be
running if you start it locally with `make run`.

The DYLD_LIBRARY_PATH thing is to get psycopg2 working on Mac OS with
EnterpriseDB's Postgres 9.1 installer.


Testing
-------

Unit and integration tests can be run using `make test`. Write unit tests for
all new code and all code you change.

**TODO:** Write a unittest teardown method that runs all the unit tests in a
transaction so we don't end up one day with a massive test database.


Setting up the Database
-----------------------

The schema for the Gittip.com database is defined in sql/schema.sql. Here's how
to install it:

    $ createuser -s gittip
    $ createdb gittip -O gittip
    $ psql gittip < schema.sql

And if you want a separate db for running unit tests:

    $ createdb gittip_test -O gittip
    $ psql gittip_test < schema.sql

The best version of Postgres to use is 9.1, because gittip uses the hstore
extension for unstructured data, and that isn't bundled with earlier versions.

If you need to make schema changes or work on the credit card workflow then
talk to me (@whit537) and we'll figure out how to get you what you need.


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
