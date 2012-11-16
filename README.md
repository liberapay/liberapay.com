This is [Gittip](https://www.gittip.com/), a sustainable crowd-funding
platform.

The basis of Gittip is an anonymous gift between $1 and $24 per week to someone
who does great work. These gifts come with no explicit strings attached.

The Gittip gift exchange happens every Thursday. On Thursday, we charge
people's credit cards and the money goes into a marketplace account with
[Balanced Payments](https://www.balancedpayments.com). Money is allocated to
other participants, and for those with a bank account attached and money due,
the money is deposited in their bank account on Friday.

Gittip is funded on Gittip.


Installation
============

Dependencies
------------

Gittip is built with [Python](http://www.python.org/) 2.7 and the
[Aspen](http://aspen.io/) web framework, and is hosted on
[Heroku](http://www.heroku.com/).
[Balanced](https://www.balancedpayments.com/) is used for payment processing,
and [Google](https://www.google.com/analytics) for analytics.

You need python2.7 on your PATH.

You need [Postgres](http://www.postgresql.org/download/). The best version to
use is 9.2, because that's what is being run in production at Heroku. Version
9.1 is the second-best, because Gittip uses the
[hstore](http://www.postgresql.org/docs/9.2/static/hstore.html) extension for
unstructured data, and that isn't bundled with earlier versions than 9.1. If
you're on a Mac, maybe try out Heroku's
[Postgres.app](http://www.postgresql.org/download/). If installing using a
package manager, you may need several packages. On Ubuntu and Debian, the
required packages are: postgresql (base), libpq5-dev (includes headers needed
to build the psycopg2 Python library), and postgresql-contrib (includes hstore)

The reason we want you to use Postgres locally instead of SQLite is so that
your development environment closely matches production, minimizing a class of
bugs (works in dev, breaks in prod). Furthermore, it's a design decision in
Gittip to use SQL, and specifically PostgreSQL, instead of an ORM. We want to
treat our database as a first-class citizen, and we want to be free to use
Postgres features such as hstore.

Now, you need to setup the database.


Setting up the Database
-----------------------

Once Postgres is installed, you need to configure it and set up a gittip
database.

First, add a "role" (Postgres user) that matches your OS username. Make sure
it's a superuser role and has login privileges. Here's a sample invocation of
the createuser executable that comes with Postgres that will do this for you,
assuming that a "postgres" superuser was already created as part of initial
installation:

    $ sudo -u postgres createuser --superuser $USER

Set the authentication method to "trust" in pg_hba.conf for all local
connections and host connections from localhost. For this, ensure that the
file contains these lines:

    local   all             all                                     trust
    host    all             all             127.0.0.1/32            trust
    host    all             all             ::1/128                 trust

Reload Postgres using pg_ctl for changes to take effect.

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


Building and Launching
----------------------

Once you've installed Python and Postgres and set up a database, you can use
make to build and launch Gittip:

    $ make run

If you don't have make, look at the Makefile to see what steps you need to
perform to build and launch Gittip. The Makefile is pretty simple and
straightforward. 

All Python dependencies (including virtualenv) are bundled with Gittip in the
vendor/ directory. Gittip is designed so that you don't manage its virtualenv
directly and you don't download its dependencies at build time.

If Gittip launches successfully it will look like this:

```
$ make run
./env/bin/swaddle local.env ./env/bin/aspen \
                --www_root=www/ \
                --project_root=.. \
                --show_tracebacks=yes \
                --changes_reload=yes \
                --network_address=:8537
[SWADDLE] Skipping line: .
[SWADDLE] Skipping line: .
[SWADDLE] Skipping line: .
[SWADDLE] Skipping line: .
[SWADDLE] Skipping line: .
pid-12508 thread-140735090330816 (MainThread) Reading configuration from defaults, environment, and command line.
pid-12508 thread-140735090330816 (MainThread)   changes_reload         False                          default                 
pid-12508 thread-140735090330816 (MainThread)   changes_reload         True                           command line option --changes_reload=yes
pid-12508 thread-140735090330816 (MainThread)   charset_dynamic        UTF-8                          default                 
pid-12508 thread-140735090330816 (MainThread)   charset_static         None                           default                 
pid-12508 thread-140735090330816 (MainThread)   configuration_scripts  []                             default                 
pid-12508 thread-140735090330816 (MainThread)   indices                [u'index.html', u'index.json', u'index'] default                 
pid-12508 thread-140735090330816 (MainThread)   list_directories       False                          default                 
pid-12508 thread-140735090330816 (MainThread)   logging_threshold      0                              default                 
pid-12508 thread-140735090330816 (MainThread)   media_type_default     text/plain                     default                 
pid-12508 thread-140735090330816 (MainThread)   media_type_json        application/json               default                 
pid-12508 thread-140735090330816 (MainThread)   network_address        ((u'0.0.0.0', 8080), 2)        default                 
pid-12508 thread-140735090330816 (MainThread)   network_address        ((u'0.0.0.0', 8537), 2)        command line option --network_address=:8537
pid-12508 thread-140735090330816 (MainThread)   network_engine         cherrypy                       default                 
pid-12508 thread-140735090330816 (MainThread)   project_root           None                           default                 
pid-12508 thread-140735090330816 (MainThread)   project_root           ..                             command line option --project_root=..
pid-12508 thread-140735090330816 (MainThread)   renderer_default       tornado                        default                 
pid-12508 thread-140735090330816 (MainThread)   show_tracebacks        False                          default                 
pid-12508 thread-140735090330816 (MainThread)   show_tracebacks        True                           command line option --show_tracebacks=yes
pid-12508 thread-140735090330816 (MainThread)   unavailable            0                              default                 
pid-12508 thread-140735090330816 (MainThread)   www_root               None                           default                 
pid-12508 thread-140735090330816 (MainThread)   www_root               www/                           command line option --www_root=www/
pid-12508 thread-140735090330816 (MainThread) project_root is relative: '..'.
pid-12508 thread-140735090330816 (MainThread) project_root set to /Your/path/to/www.gittip.com.
pid-12508 thread-140735090330816 (MainThread) Renderers (*ed are unavailable, CAPS is default):
pid-12508 thread-140735090330816 (MainThread)   TORNADO          
pid-12508 thread-140735090330816 (MainThread)  *pystache         ImportError: No module named pystache
pid-12508 thread-140735090330816 (MainThread)   stdlib_template  
pid-12508 thread-140735090330816 (MainThread)   stdlib_format    
pid-12508 thread-140735090330816 (MainThread)  *jinja2           ImportError: No module named jinja2
pid-12508 thread-140735090330816 (MainThread)   stdlib_percent   
pid-12508 thread-140735090330816 (MainThread) Starting cherrypy engine.
pid-12508 thread-140735090330816 (MainThread) Greetings, program! Welcome to port 8537.
pid-12508 thread-140735090330816 (MainThread) Aspen will restart when configuration scripts or Python modules change.
pid-12508 thread-140735090330816 (MainThread) Starting up Aspen website.
```

You should then find this in your browser at http://localhost:8537/:

![Success](https://raw.github.com/whit537/www.gittip.com/master/img-src/success.png)

Congratulations! Click "Sign in with GitHub" and you're off and running. At
some point, try [running the test suite](#testing).


Help!
-----

If it doesn't, you can find help in the #gittip channel on
[Freenode](http://webchat.freenode.net/) or in the [issue
tracker](/whit537/www.gittip.com/issues/new) here on GitHub. If all else fails
ping [@whit537](https://twitter.com/whit537) on Twitter.

Thanks for installing Gittip! :smiley: 


Configuration
=============

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


Testing [![Testing](https://secure.travis-ci.org/whit537/www.gittip.com.png)](http://travis-ci.org/whit537/www.gittip.com)
=======

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
into a commit. Once their changeset was deployed, we would have ... problems.
Of course, they could also remove the check in the same or even a different
commit. Of course, they could also sneak in whatever the heck code they wanted
to try to sneak in.

To invoke nosetests directly you should use the `swaddle` utility that comes
with Aspen. First `make tests/env`, edit it as noted above, and then:

    [gittip] $ cd tests/
    [gittip] $ swaddle env ../env/bin/nosetests


See Also
========

Here's a list of projects we're aware of in the crowd-funding space. Something
missing? Ping [@whit537](https://twitter.com/whit537) on Twitter or [edit the
file](/whit537/www.gittip.com/edit/master/README.md) yourself (add your link at
the end). :grinning:

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
