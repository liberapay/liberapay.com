# Welcome to Gittip [<img height="26px" src="www/assets/gittip.opengraph.png"/>](https://www.gittip.com/)

[![Build Status](http://img.shields.io/travis/gittip/www.gittip.com/master.svg)](https://travis-ci.org/gittip/www.gittip.com)
[![HuBoard badge](http://img.shields.io/badge/Hu-Board-7965cc.svg)](https://huboard.com/gittip/www.gittip.com)

Gittip is a weekly gift exchange, helping to create a culture of generosity.
If you'd like to learn more, check out <https://gittip.com/about>.
If you'd like to contribute to Gittip, the best first reference is <https://gittip.com/for/contributors>.

Quick Start
===========

```
$ git clone git@github.com:gittip/www.gittip.com.git
$ cd www.gittip.com
$ sudo -u postgres createuser --superuser $USER
$ createdb gittip
$ make schema
$ make run
```

And/or:

```
$ make test
```

We also include a
[Vagrantfile](https://github.com/gittip/www.gittip.com/blob/master/Vagrantfile).


Table of Contents
=================

 - [Installation](#installation)
  - [Dependencies](#dependencies)
  - [Building](#building)
  - [Launching](#launching)
  - [Help!](#help)
 - [Configuration](#configuration)
 - [Modifying CSS](#modifying-css)
 - [Testing](#testing-)
 - [Setting up a Database](#local-database-setup)
 - [API](#api)
  - [Implementations](#api-implementations)
 - [Glossary](#glossary)
 - [See Also](#see-also)


Installation
============

Thanks for hacking on Gittip! Be sure to review
[CONTRIBUTING](https://github.com/gittip/www.gittip.com/blob/master/CONTRIBUTING.md#readme)
as well if that's what you're planning to do.


Dependencies
------------

Building `www.gittip.com` requires [Python
2.7](http://python.org/download/releases/2.7.4/), and a gcc/make toolchain.

All Python library dependencies are bundled in the repo (under `vendor/`) and
if you do not want to install Postgres locally you can try to use a cloud instance
by issuing `make cloud-db` (it is somewhat slow for regular development).

To configure local Postgres create default role and database:

    $ sudo -u postgres createuser --superuser $USER
    $ createdb gittip

On Debian or Ubuntu you will need the following packages:
`libpq5-dev`/`libpq-dev`, (includes headers needed to build the `psycopg2` Python library)
and `python-dev` (includes Python header files for `psycopg2`).

If you are receiving issues from `psycopg2`, please [ensure that its needs are
met](http://initd.org/psycopg/docs/faq.html#problems-compiling-and-deploying-psycopg2).

If you are getting an error about `unknown argument: '-mno-fused-madd'` when
running `make`, then add
`Wno-error=unused-command-line-argument-hard-error-in-future` to your
`ARCHFLAGS` environment variable and try again (see [this Stack Overflow answer
for more information](http://stackoverflow.com/a/22355874/347246)):

    $ ARCHFLAGS=-Wno-error=unused-command-line-argument-hard-error-in-future

Building
--------

All Python dependencies (including virtualenv) are bundled with Gittip in the
vendor/ directory. Gittip is designed so that you don't manage its
virtualenv directly and you don't download its dependencies at build
time.

The included `Makefile` contains several targets. Configuration options
are stored in default_local.env file while overrides are in local.env.

To create virtualenv enviroment with all python dependencies installed
in a sandbox:

    $ make env

If you haven't run Gittip for a while, you can reinstall the dependencies:

    $ make clean env

Add the necessary schemas and insert dummy data into postgres:

    $ make schema
    $ make data


Launching
---------

Once you've installed Python and Postgres and set up a database, you can use
make to build and launch Gittip:

    $ make run

If you don't have make, look at the Makefile to see what steps you need
to perform to build and launch Gittip. The Makefile is pretty simple and
straightforward.

If Gittip launches successfully it will look like this:

```
$ make run
./env/bin/honcho -e default_local.env,local.env run ./env/bin/aspen
pid-27937 thread-47041048338176 (MainThread) Reading configuration from defaults, environment, and command line.
pid-27937 thread-47041048338176 (MainThread)   changes_reload         False                          default
pid-27937 thread-47041048338176 (MainThread)   changes_reload         True                           environment variable ASPEN_CHANGES_RELOAD=1
pid-27937 thread-47041048338176 (MainThread)   charset_dynamic        UTF-8                          default
pid-27937 thread-47041048338176 (MainThread)   charset_static         None                           default
pid-27937 thread-47041048338176 (MainThread)   configuration_scripts  []                             default
pid-27937 thread-47041048338176 (MainThread)   indices                [u'index.html', u'index.json', u'index', u'index.html.spt', u'index.json.spt', u'index.spt'] default
pid-27937 thread-47041048338176 (MainThread)   list_directories       False                          default
pid-27937 thread-47041048338176 (MainThread)   logging_threshold      0                              default
pid-27937 thread-47041048338176 (MainThread)   media_type_default     text/plain                     default
pid-27937 thread-47041048338176 (MainThread)   media_type_json        application/json               default
pid-27937 thread-47041048338176 (MainThread)   network_address        ((u'0.0.0.0', 8080), 2)        default
pid-27937 thread-47041048338176 (MainThread)   network_address        ((u'0.0.0.0', 8537), 2)        environment variable ASPEN_NETWORK_ADDRESS=:8537
pid-27937 thread-47041048338176 (MainThread)   network_engine         cheroot                        default
pid-27937 thread-47041048338176 (MainThread)   project_root           None                           default
pid-27937 thread-47041048338176 (MainThread)   project_root           .                              environment variable ASPEN_PROJECT_ROOT=.
pid-27937 thread-47041048338176 (MainThread)   renderer_default       stdlib_percent                 default
pid-27937 thread-47041048338176 (MainThread)   show_tracebacks        False                          default
pid-27937 thread-47041048338176 (MainThread)   show_tracebacks        True                           environment variable ASPEN_SHOW_TRACEBACKS=1
pid-27937 thread-47041048338176 (MainThread)   www_root               None                           default
pid-27937 thread-47041048338176 (MainThread)   www_root               www/                           environment variable ASPEN_WWW_ROOT=www/
pid-27937 thread-47041048338176 (MainThread) project_root is relative to CWD: '.'.
pid-27937 thread-47041048338176 (MainThread) project_root set to /home/zbynek/www.gittip.com.
pid-27937 thread-47041048338176 (MainThread) Found plugin for renderer 'jinja2'
pid-27937 thread-47041048338176 (MainThread) Won't log to Sentry (SENTRY_DSN is empty).
pid-27937 thread-47041048338176 (MainThread) Loading configuration file '/home/zbynek/www.gittip.com/configure-aspen.py' (possibly changing settings)
pid-27937 thread-47041048338176 (MainThread) Renderers (*ed are unavailable, CAPS is default):
pid-27937 thread-47041048338176 (MainThread)   stdlib_percent
pid-27937 thread-47041048338176 (MainThread)   stdlib_format
pid-27937 thread-47041048338176 (MainThread)   JINJA2
pid-27937 thread-47041048338176 (MainThread)   stdlib_template
pid-27937 thread-47041048338176 (MainThread) Starting cheroot engine.
pid-27937 thread-47041048338176 (MainThread) Greetings, program! Welcome to port 8537.
pid-27937 thread-47041048338176 (MainThread) Aspen will restart when configuration scripts or Python modules change.
pid-27937 thread-47041048338176 (MainThread) Starting up Aspen website.
```

You should then find this in your browser at
[http://localhost:8537/](http://localhost:8537/):

![Success](https://raw.github.com/gittip/www.gittip.com/master/img-src/success.png)

Congratulations! Sign in using Twitter or GitHub and you're off and
running. At some point, try [running the test suite](#testing-).


Help!
-----

If you get stuck somewhere along the way, you can find help in the #gittip
channel on [Freenode](http://webchat.freenode.net/) or in the [issue
tracker](/gittip/www.gittip.com/issues/new) here on GitHub. If all else fails
ping [@whit537](https://twitter.com/whit537) on Twitter or email
[chad@gittip.com](mailto:chad@gittip.com).

Thanks for installing Gittip! :smiley:


Configuration
=============

When using `make run`, Gittip's execution environment is defined in an
environment files [default_local.env]
(https://github.com/gittip/www.gittip.com/blob/master/default_local.env)
`local.env`. The former contains all variables needed to run successfully.
The later allows for easy overrides since it is not included in the source
code repo.

The following text explains some of the content of that file:

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

You probably don't need it, but at one point I had to set this to get
psycopg2 working on Mac OS with EnterpriseDB's Postgres 9.1 installer:

    DYLD_LIBRARY_PATH=/Library/PostgreSQL/9.1/lib

If you wish to use different username or database name for the database, you
should change the `DATABASE_URL` using the following format:

    DATABASE_URL=postgres://<username>@localhost/<database name>

Modifying CSS
=============

We use SCSS, with files stored in `scss/`. All of the individual files are
combined in `scss/gittip.scss` which itself is compiled by `libsass` in
`www/assets/%version/gittip.css.spt` on each request.

Testing [![Build Status](http://img.shields.io/travis/gittip/www.gittip.com/master.svg)](https://travis-ci.org/gittip/www.gittip.com)
=======

Please write unit tests for all new code and all code you change.  Gittip's
test suite uses the py.test test runner, which will be installed into the
virtualenv you get by running `make env`. As a rule of thumb, each test case
should perform one assertion.

The easiest way to run the test suite is:

    $ make test

However, the test suite deletes data in all tables in the public schema of the
database configured in your testing environment.

To invoke py.test directly you should use the `honcho` utility that comes
with the install. First `make tests/env`, activate the virtualenv and then:

    [gittip] $ cd tests/
    [gittip] $ honcho -e ../default_tests.env,env py.test

The tests will try to use `gittip-test` database of the current $USER.


Local Database Setup
--------------------

For the best development experience, you need a local
installation of [Postgres](http://www.postgresql.org/download/). The best
version of Postgres to use is 9.3.2, because that's what we're using in
production at Heroku. You need at least 9.2, because we depend on being able to
specify a URI to `psql`, and that was added in 9.2.

If you're on a Mac, maybe try out Heroku's
[Postgres.app](http://www.postgresql.org/download/). If installing using a
package manager, you may need several packages. On Ubuntu and Debian, the
required packages are: `postgresql` (base) and `postgresql-contrib` (includes hstore).

To setup the instance for gittip's needs run:

    $ sudo -u postgres createuser --superuser $USER
    $ createdb gittip
    $ createdb gittip-test

You can speed up the test suite when using a regular HDD by running:

    $ psql -q gittip-test -c 'alter database "gittip-test" set synchronous_commit to off'

### Schema

Once Postgres is set up, run:

    $ make schema

That will populate the database named by DATABASE_URL with the Gittip schema,
per ./schema.sql.

The schema for the Gittip.com database is defined in schema.sql. It should be
considered append-only. The idea is that this is the log of DDL that
we've run against the production database. You should never change
commands that have already been run. New DDL will be (manually) run against the
production database as part of deployment.


### Example data

The gittip database created in the last step is empty. To populate it with
some fake data, so that more of the site is functional, run this command:

    $ make data


API
===

The Gittip API is comprised of these six endpoints:

**[/about/charts.json](https://www.gittip.com/about/charts.json)**
([source](https://github.com/gittip/www.gittip.com/tree/master/www/about/charts.json.spt))&mdash;<i>public</i>&mdash;Returns
an array of objects, one per week, showing aggregate numbers over time. The
[charts](https://www.gittip.com/about/charts.html) page uses this.

**[/about/paydays.json](https://www.gittip.com/about/paydays.json)**
([source](https://github.com/gittip/www.gittip.com/tree/master/www/about/paydays.json.spt))&mdash;<i>public</i>&mdash;Returns
an array of objects, one per week, showing aggregate numbers over time. The
[charts](https://www.gittip.com/about/charts.html) page used to use this.

**[/about/stats.json](https://www.gittip.com/about/stats.json)**
([source](https://github.com/gittip/www.gittip.com/tree/master/www/about/stats.spt))&mdash;<i>public</i>&mdash;Returns
an object giving a point-in-time snapshot of Gittip. The
[stats](https://www.gittip.com/about/stats.html) page displays the same info.

**/`%username`/charts.json**
([example](https://www.gittip.com/Gittip/charts.json),
[source](https://github.com/gittip/www.gittip.com/tree/master/www/%25username/charts.json.spt))&mdash;<i>public</i>&mdash;Returns
an array of objects, one per week, showing aggregate numbers over time for the
given user.

**/`%username`/public.json**
([example](https://www.gittip.com/Gittip/public.json),
[source](https://github.com/gittip/www.gittip.com/tree/master/www/%25username/public.json.spt))&mdash;<i>public</i>&mdash;Returns an object with these keys:

  - "receiving"&mdash;an estimate of the amount the given participant will
    receive this week

  - "my_tip"&mdash;logged-in user's tip to the Gittip participant in
    question; possible values are:

      - `undefined` (key not present)&mdash;there is no logged-in user
      - "self"&mdash;logged-in user is the participant in question
      - `null`&mdash;user has never tipped this participant
      - "0.00"&mdash;user used to tip this participant
      - "3.00"&mdash;user tips this participant the given amount
      <br><br>

  - "goal"&mdash;funding goal of the given participant; possible values are:

      - `undefined` (key not present)&mdash;participant is a patron (or has 0 as the goal)
      - `null`&mdash;participant is grateful for gifts, but doesn't have a specific funding goal
      - "100.00"&mdash;participant's goal is to receive the given amount per week
      <br><br>

  - "elsewhere"&mdash;participant's connected accounts elsewhere; returns an object with these keys:

      - "bitbucket"&mdash;participant's Bitbucket account; possible values are:
          - `undefined` (key not present)&mdash;no Bitbucket account connected
          - `https://bitbucket.org/api/1.0/users/%bitbucket_username`
      - "github"&mdash;participant's GitHub account; possible values are:
          - `undefined` (key not present)&mdash;no GitHub account connected
          - `https://api.github.com/users/%github_username`
      - "twitter"&mdash;participant's Twitter account; possible values are:
          - `undefined` (key not present)&mdash;no Twitter account connected
          - `https://api.twitter.com/1.1/users/show.json?id=%twitter_immutable_id&include_entities=1`
      - "openstreetmap"&mdash;participant's OpenStreetMap account; possible values are:
          - `undefined` (key not present)&mdash;no OpenStreetMap account connected
          - `%OPENSTREETMAP_API/user/%openstreetmap_username`


**/`%username`/tips.json**
([source](https://github.com/gittip/www.gittip.com/tree/master/www/%25username/tips.json.spt))&mdash;<i>private</i>&mdash;Responds
to `GET` with an array of objects representing your current tips. `POST` the
same structure back in order to update tips in bulk (be sure to set
`Content-Type` to `application/json` instead of
`application/x-www-form-urlencoded`). You can `POST` a partial array to update
a subset of your tips. The response to a `POST` will be only the subset you
updated. If the `amount` is `"error"` then there will also be an `error`
attribute with a one-word error code. If you include an `also_prune` key in the
querystring (not the body!) with a value of `yes`, `true`, or `1`, then any
tips not in the array you `POST` will be zeroed out.

NOTE: The amounts must be encoded as a string (rather than a number).
Additionally, currently, the only supported platform is 'gittip'.

This endpoint requires authentication. Look for your API key on your [profile
page](https://www.gittip.com/about/me.html), and pass it as the basic auth
username. E.g.:

```
curl https://www.gittip.com/foobar/tips.json \
    -u API_KEY: \
    -X POST \
    -d'[{"username":"bazbuz", "platform":"gittip", "amount": "1.00"}]' \
    -H"Content-Type: application/json"
```

API Implementations
-------------------

Below are some projects that use the Gittip APIs, that can serve as inspiration
for your project!

 - [Drupal: Gittip](https://drupal.org/project/gittip)&mdash;Includes a Gittip
   giving field type to let you implement the Khan academy model for users on
   your Drupal site.

 - [Node.js: Node-Gittip](https://npmjs.org/package/gittip) (also see [Khan
   Academy's setup](http://ejohn.org/blog/gittip-at-khan-academy/))

 - [Ruby: gratitude](https://github.com/JohnKellyFerguson/gratitude): A ruby gem that wraps the Gittip API (currently in development and not feature complete).

 - [WordPress: WP-Gittip](https://github.com/daankortenbach/WP-Gittip)

 - [hubot-gittip](https://github.com/myplanetdigital/hubot-gittip): A Hubot script for interacting with a shared Gittip account.

 - [gittip-collab](https://github.com/engineyard/gittip-collab): A Khan-style tool for managing a Gittip account as a team.

Glossary
========

**Account Elsewhere** - An entity's registration on a platform other than
Gittip (e.g., Twitter).

**Entity** - An entity.

**Participant** - An entity registered with Gittip.

**User** - A person using the Gittip website. Can be authenticated or
anonymous. If authenticated, the user is guaranteed to also be a participant.


See Also
========

Here's a list of projects we're aware of in the crowd-funding
space. Something missing? Ping [@whit537](https://twitter.com/whit537) on
Twitter or [edit the file](https://github.com/gittip/www.gittip.com/edit/master/README.md)
yourself (add your link at the end). :grinning:

*Note: there are comprehensive directories that can complement this list,
such as [startingtrends.com's](http://www.startingtrends.com/crowdfunding-directory/)
and [crowdsourcing.org's](http://www.crowdsourcing.org/directory)*

 - [Kickstarter](http://www.kickstarter.com/) - crowdfunding campaigns
 - [Flattr](http://flattr.com/) - micro-donations (flat monthly rate)
 - [TipTheWeb](http://tiptheweb.org/) - micro-donations
 - [IndieGoGo](http://www.indiegogo.com/) - crowdfunding campaigns (partial funding allowed)
 - [PledgeMusic](http://www.pledgemusic.com/) - crowdfunding for musicians
 - [Propster](https://propster.me/)
 - [Kachingle](http://kachingle.com/)
 - [Venmo](https://venmo.com/) - transactions among friends (US only)
 - [Snoball](https://www.snoball.com/) - link events or actions as triggers for micro-donations
 - [Pledgie](http://pledgie.com/) - crowdfunding campaigns
 - [HumbleBundle](http://www.humblebundle.com/)
 - [CrowdTilt](https://www.crowdtilt.com/) - crowdfunding campaigns
 - [NetworkForGood](http://www1.networkforgood.org/)
 - [AnyFu](http://anyfu.com/) - hire an expert for one-on-one, screen-share work sessions
 - [OpenOfficeHours](http://ohours.org/)
 - [discontinued] [TipJoy](http://techcrunch.com/2009/08/20/tipjoy-heads-to-the-deadpool/)
 - [HopeMob](http://hopemob.org/)
 - [AwesomeFoundation](http://www.awesomefoundation.org/)
 - [CrowdRise](http://www.crowdrise.com/)
 - [discontinued] [ChipIn](http://www.chipin.com/)
 - [Fundable](http://www.fundable.com/) - fund start-up companies
 - [ModestNeeds](https://www.modestneeds.org/) - crowdfunding campaigns in support of the &ldquo;working poor&rdquo;
 - [FreedomSponsors](http://www.freedomsponsors.org/) - Crowdfunding Free Software, one issue at a time
 - [GumRoad](https://gumroad.com/)
 - [MacHeist](http://macheist.com/)
 - [Prosper](http://www.prosper.com/) - peer-to-peer lending
 - [discontinued] [Togather](http://togather.me/)
 - [PaySwarm](http://payswarm.com/) - open payment protocol
 - [discontinued] [Gitbo](http://git.bo/) - another implementation of the bounty model
 - [Affero](http://www.affero.com/) - old skool attempt &ldquo;to bring a culture of patronage to the Internet&rdquo;
 - [ShareAGift](http://www.shareagift.com) - one-off, crowd-sourced cash gifts
 - [GoFundMe](http://www.gofundme.com/) - derpy-looking platform that [reaches normal people](http://pittsburgh.cbslocal.com/2013/02/19/crowdfunding-growing-in-popularity-as-fundraising-tool/) (my dad emailed this link to me)
 - [DonorsChoose.org](http://www.donorschoose.org/) - crowd-funded school
    supplies; Alexis Ohanian
    [likes it](http://www.donorschoose.org/AlexisOnCNN).
 - [Catincan](https://www.catincan.com/) - FOSS bounty site
 - [Bountysource](https://www.bountysource.com/) - FOSS bounty site
 - [IssueHunter](http://issuehunter.co/) - FOSS bounty site
 - [TinyPass](http://www.tinypass.com/) - Soft paywall, used by e.g. [Daily Dish](http://dish.andrewsullivan.com/)
 - [Patreon](http://www.patreon.com/) - Patronage model for content creators(!)
 - [discontinued] [WhyNotMe](http://www.whynotme.me/) - "Give as a group to any non-profit in America"
 - [LoveMachine](http://web.archive.org/web/20110214110248/http://sendlove.us/trial/faq.php) - "the cool new employee recognition system" (supposedly came out of Linden Lab)
 - [See.Me](https://www.see.me/) - sustainable crowdfunding for artists
 - [NoiseTrade](http://www.noisetrade.com/) - band mailing lists + tips
 - [YouTube Nonprofit Program](http://www.youtube.com/nonprofits) - puts donate buttons on your vids
 - [Generous](http://genero.us/) - Pay-what-you-want platform
 - [FundAnything](http://fundanything.com/) - Kickstarter knock-off, I guess?
 - [ShareTribe](https://www.sharetribe.com/) - Create your own community marketplace
 - [Subbable](https://subbable.com/) - What John and Hank Green wanted (cf. [#737](https://github.com/gittip/www.gittip.com/issues/737))
 - [Pitch In](http://pitchinbox.com/) - Widget-centric project-based funding campaigns
 - [Binpress](http://www.binpress.com/) - Binpress is the marketplace for commercial open-source projects.
 - [TubeStart](https://www.tubestart.com/) - a crowdfunding platform dedicated exclusively to YouTube creators
 - [Fundit](http://www.fundit.ie/) - An Ireland-wide initiative
 - [Snowdrift.coop](https://snowdrift.coop/) - a new sustainable patronage system
 - [PieTrust](http://www.pietrust.com/) - an "open company" developing a secure reputation system for sharing credit.
 - [BountyOSS](https://bountyoss.com/) - Where crowdfunding means business
 - [Suprmasv](https://www.suprmasv.com/) - Empowering the Hacker Class.
 - [Tip4Commit](http://tip4commit.com/) - Donate bitcoins to open source projects or make commits and get tips for it.
 - [BitHub](https://whispersystems.org/blog/bithub/) - An experiment in funding privacy OSS.
 - [Fundly](https://fundly.com/) - Crowdfund Anything
 - [I Love Open Source](http://www.iloveopensource.io/) - Simple recognition for open source developers
 - [Razoo](http://www.razoo.com/) - Create online fundraisers for anything and everything that matters to you.
 - [CoinGiving](http://coingiving.com/) - Personified Bitcoin Donations
 - [Bittip](http://bittip.it/) - Bitcoin Microdonations - Like Flattr, but with Btc
 - [MedStartr](http://www.medstartr.com/) - Fund the medical breakthroughs and innovations you care about
 - [Upstart](https://www.upstart.com/) - Raise money from your future self
 - [Gitcoin](http://www.gitcoin.co/) - Give bitcoin donations to your favorite projects.
 - [Patronism](http://patronism.com/) - Become a patron of your favorite band.
 - [Beacon](http://www.beaconreader.com/) - Fund one writer for $5 a month
