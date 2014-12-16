# Welcome to Gratipay [<img height="26px" src="https://raw.githubusercontent.com/gratipay/gratipay.com/master/www/assets/gratipay.opengraph.png"/>](https://gratipay.com/)

[![Build Status](http://img.shields.io/travis/gratipay/gratipay.com/master.svg)](https://travis-ci.org/gratipay/gratipay.com)
[![Coverage Status](https://img.shields.io/coveralls/gratipay/gratipay.com.svg)](https://coveralls.io/r/gratipay/gratipay.com?branch=master)
[![HuBoard badge](http://img.shields.io/badge/Hu-Board-7965cc.svg)](https://huboard.com/gratipay/gratipay.com)
[![Open Bounties](https://api.bountysource.com/badge/team?team_id=423&style=bounties_received)](https://www.bountysource.com/teams/gratipay/issues)

[Gratipay](http://gratipay.com) is a weekly gift exchange, helping to create a culture of generosity.
If you'd like to learn more, check out <https://gratipay.com/about>.
If you'd like to contribute to Gratipay, check out <http://inside.gratipay.com>.

Quick Start
===========

Local
-----

Given Python 2.7, Postgres 9.3, and a C/make toolchain:

```
$ git clone git@github.com:gratipay/gratipay.com.git
$ cd gratipay.com
$ sudo -u postgres createuser --superuser $USER
$ createdb gratipay
$ make schema data
$ make run
```

And/or:

```
$ make test
```

[Read more](#table-of-contents).


Vagrant
-------

Given VirtualBox 4.3 and Vagrant 1.6.x:

```
$ vagrant up
```

[Read more](#vagrant-1).


Docker
-------

Given some version(?) of Docker:

```
$ docker build -t gratipay .
$ docker run -p 8537:8537 gratipay
```

[Read more](#docker-1).


Table of Contents
=================

 - [Installation](#installation)
  - [Dependencies](#dependencies)
  - [Building](#building)
  - [Launching](#launching)
  - [Configuring](#configuring)
  - [Vagrant](#vagrant)
  - [Docker](#docker)
  - [Help!](#help)
 - [Configuration](https://github.com/gratipay/gratipay.com/wiki/Configuration)
 - [Modifying CSS](#modifying-css)
 - [Modifying the Database](#modifying-the-database)
 - [Testing](#testing-)
 - [Setting up a Database](#local-database-setup)
 - [API](#api)
  - [Implementations](#api-implementations)
 - [Glossary](#glossary)


Installation
============

Thanks for hacking on Gratipay! Be sure to review
[CONTRIBUTING](https://github.com/gratipay/gratipay.com/blob/master/CONTRIBUTING.md#readme)
as well if that's what you're planning to do.


Dependencies
------------

Building `gratipay.com` requires [Python
2.7](http://python.org/download/releases/2.7.4/), and a gcc/make toolchain.

All Python library dependencies are bundled in the repo (under `vendor/`). If
you are receiving issues from `psycopg2`, please [ensure that its needs are
met](http://initd.org/psycopg/docs/faq.html#problems-compiling-and-deploying-psycopg2).

On Debian or Ubuntu you will need the following packages:

    $ sudo apt-get install postgresql-9.3 postgresql-contrib libpq-dev python-dev

To configure local Postgres create default role and database:

    $ sudo -u postgres createuser --superuser $USER
    $ createdb gratipay

If you are getting an error about `unknown argument: '-mno-fused-madd'` when
running `make`, then add
`Wno-error=unused-command-line-argument-hard-error-in-future` to your
`ARCHFLAGS` environment variable and run `make clean env` again (see [this Stack Overflow answer
for more information](http://stackoverflow.com/a/22355874/347246)):

    $ ARCHFLAGS=-Wno-error=unused-command-line-argument-hard-error-in-future make clean env


Building
--------

All Python dependencies (including virtualenv) are bundled with Gratipay in the
vendor/ directory. Gratipay is designed so that you don't manage its
virtualenv directly and you don't download its dependencies at build
time.

The included `Makefile` contains several targets. Configuration options
are stored in default_local.env file while overrides are in local.env.

To create virtualenv enviroment with all python dependencies installed
in a sandbox:

    $ make env

If you haven't run Gratipay for a while, you can reinstall the dependencies:

    $ make clean env

Add the necessary schemas and insert dummy data into postgres:

    $ make schema
    $ make data


Launching
---------

Once you've installed Python and Postgres and set up a database, you can use
make to build and launch Gratipay:

    $ make run

If you don't have make, look at the Makefile to see what steps you need
to perform to build and launch Gratipay. The Makefile is pretty simple and
straightforward.

If Gratipay launches successfully it will look like this:

```
$ make run
PATH=env/bin:{lots-more-of-your-own-PATH} env/bin/honcho run -e defaults.env,local.env web
2014-07-22 14:53:09 [1258] [INFO] Starting gunicorn 18.0
2014-07-22 14:53:09 [1258] [INFO] Listening at: http://0.0.0.0:8537 (1258)
2014-07-22 14:53:09 [1258] [INFO] Using worker: sync
2014-07-22 14:53:09 [1261] [INFO] Booting worker with pid: 1261
pid-1261 thread-140735191843600 (MainThread) Reading configuration from defaults, environment, and command line.
pid-1261 thread-140735191843600 (MainThread)   changes_reload         False                          default
pid-1261 thread-140735191843600 (MainThread)   changes_reload         True                           environment variable ASPEN_CHANGES_RELOAD=yes
pid-1261 thread-140735191843600 (MainThread)   charset_dynamic        UTF-8                          default
pid-1261 thread-140735191843600 (MainThread)   charset_static         None                           default
pid-1261 thread-140735191843600 (MainThread)   configuration_scripts  []                             default
pid-1261 thread-140735191843600 (MainThread)   indices                [u'index.html', u'index.json', u'index', u'index.html.spt', u'index.json.spt', u'index.spt'] default
pid-1261 thread-140735191843600 (MainThread)   list_directories       False                          default
pid-1261 thread-140735191843600 (MainThread)   logging_threshold      0                              default
pid-1261 thread-140735191843600 (MainThread)   media_type_default     text/plain                     default
pid-1261 thread-140735191843600 (MainThread)   media_type_json        application/json               default
pid-1261 thread-140735191843600 (MainThread)   project_root           None                           default
pid-1261 thread-140735191843600 (MainThread)   project_root           .                              environment variable ASPEN_PROJECT_ROOT=.
pid-1261 thread-140735191843600 (MainThread)   renderer_default       stdlib_percent                 default
pid-1261 thread-140735191843600 (MainThread)   show_tracebacks        False                          default
pid-1261 thread-140735191843600 (MainThread)   show_tracebacks        True                           environment variable ASPEN_SHOW_TRACEBACKS=yes
pid-1261 thread-140735191843600 (MainThread)   www_root               None                           default
pid-1261 thread-140735191843600 (MainThread)   www_root               www/                           environment variable ASPEN_WWW_ROOT=www/
pid-1261 thread-140735191843600 (MainThread) project_root is relative to CWD: '.'.
pid-1261 thread-140735191843600 (MainThread) project_root set to /Users/whit537/personal/gratipay/gratipay.com.
pid-1261 thread-140735191843600 (MainThread) Found plugin for renderer 'jinja2'
pid-1261 thread-140735191843600 (MainThread) Won't log to Sentry (SENTRY_DSN is empty).
pid-1261 thread-140735191843600 (MainThread) Renderers (*ed are unavailable, CAPS is default):
pid-1261 thread-140735191843600 (MainThread)   stdlib_percent
pid-1261 thread-140735191843600 (MainThread)   json_dump
pid-1261 thread-140735191843600 (MainThread)   stdlib_format
pid-1261 thread-140735191843600 (MainThread)   JINJA2
pid-1261 thread-140735191843600 (MainThread)   stdlib_template
```

You should then find this in your browser at
[http://localhost:8537/](http://localhost:8537/):

![Success](https://raw.github.com/gratipay/gratipay.com/master/img-src/success.png)

Congratulations! Sign in using Twitter or GitHub and you're off and
running. At some point, try [running the test suite](#testing-).

Configuring
-----------

Gratipay's default configuration lives in [`defaults.env`](https://github.com/gratipay/gratipay.com/blob/master/defaults.env).
If you'd like to override some settings, create a file named `local.env` to store them.

The following explains some of the content of that file:

The `BALANCED_API_SECRET` is a test marketplace. To generate a new secret for
your own testing run this command:

    curl -X POST https://api.balancedpayments.com/v1/api_keys | grep secret

Grab that secret and also create a new marketplace to test against:

    curl -X POST https://api.balancedpayments.com/v1/marketplaces -u <your_secret>:

The site works without this, except for the credit card page. Visit the
[Balanced Documentation](https://www.balancedpayments.com/docs) if you want to
know more about creating marketplaces.

The `GITHUB_*` keys are for a gratipay-dev application in the Gratipay
organization on Github. It points back to localhost:8537, which is where
Gratipay will be running if you start it locally with `make run`. Similarly
with the `TWITTER_*` keys, but there they required us to spell it `127.0.0.1`.

If you wish to use a different username or database name for the database, you
should override the `DATABASE_URL` in `local.env` using the following format:

    DATABASE_URL=postgres://<username>@localhost/<database name>

The `MANDRILL_KEY` value in `defaults.env` is for a test mail server, which
won't actually send email to you. If you need to receive email during
development then sign up for an account of your own at
[Mandrill](http://mandrill.com/) and override `MANDRILL_KEY` in your
`local.env`.


Vagrant
-------
If you have Vagrant installed, you can run Gratipay by running `vagrant up` from the project directory. Please note that if you ever switch between running Gratipay on your own machine to Vagrant or vice versa, you will need to run `make clean`.

If you're using Vagrant for the first time you'll need [Vagrant](http://www.vagrantup.com/) and [VirtualBox](https://www.virtualbox.org/) installed. If you're on Linux you'll need to install `nfs-kernel-server`.

The `Vagrantfile` will download a custom made image from the Internet. If you have a slow internet connection, you can download a local copy of this file, by running:

`curl https://downloads.gratipay.com/gratipay.box`

Once downloaded into the top of the project tree, our Vagrantfile will use this local file automatically when you run `vagrant up`. Vagrant is setup to use key based SSH authentication, if you're prompted for a password when logging in please use `vagrant`.

**Mac users:** If you're prompted for a password during initial installation, it's sudo and you should enter your Mac OS password.

**Ubuntu users:** If you experience problems, please see [this
issue](https://github.com/gratipay/gratipay.com/pull/2321#issuecomment-41455169).
As mentioned, you will also need to be wary of projects that are nested
in encrypted directories.

Docker
------------

You can also install/run Gratipay with Docker.

Either pull the image from the Docker Index:

```
$ docker pull citruspi/gratipay
```

or build it with the included Dockerfile:

```
$ git clone git@github.com:gratipay/gratipay.com.git
$ cd gratipay.com
$ docker build -t gratipay .
```

Once you have the image, get the Image ID with

```
$ docker images
```


You can then run it in the foreground:

```
$ docker run -p 8537:8537 [image_id]
```

or in the background:

```
$ docker run -d -p 8537:8537 [image_id]
```

Check it out at [localhost:8537](localhost:8537)!

If you run it in the background, you can get the Container ID with

```
$ docker ps
```

With that, you can view the logs:

```
$ docker logs [container_id]
```

or kill the detached container with:

```
$ docker kill [container_id]
```


Help!
-----

If you get stuck somewhere along the way, you can find help in the #gratipay
channel on [Freenode](http://webchat.freenode.net/) or in the [issue
tracker](/gratipay/gratipay.com/issues/new) here on GitHub.

Thanks for installing Gratipay! :smiley:


Modifying CSS
=============

We use SCSS, with files stored in `scss/`. All of the individual files are
combined in `scss/gratipay.scss` which itself is compiled by `libsass` in
`www/assets/%version/gratipay.css.spt` on each request.


Modifying the Database
======================

We write SQL, specifically the [PostgreSQL
variant](http://www.postgresql.org/docs/9.3/static/). We keep our database
schema in
[`schema.sql`](https://github.com/gratipay/gratipay.com/blob/master/schema.sql),
and we write schema changes for each PR branch in a `branch.sql` file, which
then gets run against production and appended to `schema.sql` during
deployment.


Testing [![Build Status](http://img.shields.io/travis/gratipay/gratipay.com/master.svg)](https://travis-ci.org/gratipay/gratipay.com)
=======

Please write unit tests for all new code and all code you change. Gratipay's
test suite uses the py.test test runner, which will be installed into the
virtualenv you get by running `make env`. As a rule of thumb, each test case
should perform one assertion.

The easiest way to run the test suite is:

    $ make test

However, the test suite deletes data in all tables in the public schema of the
database configured in your testing environment.

To invoke py.test directly you should use the `honcho` utility that comes
with the install. First `make tests/env`, activate the virtualenv and then:

    [gratipay] $ cd tests/
    [gratipay] $ honcho run -e defaults.env,local.env py.test

Local Database Setup
--------------------

For the best development experience, you need a local
installation of [Postgres](http://www.postgresql.org/download/). The best
version of Postgres to use is 9.3.2, because that's what we're using in
production at Heroku. You need at least 9.2, because we depend on being able to
specify a URI to `psql`, and that was added in 9.2.

+ Mac: use Homerew: `brew install postgres`
+ Ubuntu: use Apt: `apt-get install postgresql postgresql-contrib libpq-dev`

To setup the instance for gratipay's needs run:

    $ sudo -u postgres createuser --superuser $USER
    $ createdb gratipay
    $ createdb gratipay-test

You can speed up the test suite when using a regular HDD by running:

    $ psql -q gratipay-test -c 'alter database "gratipay-test" set synchronous_commit to off'

### Schema

Once Postgres is set up, run:

    $ make schema

Which populates the database named by `DATABASE_URL` with the schema from `schema.sql`.

The `schema.sql` file should be considered append-only. The idea is that it's the log
of DDL that we've run against the production database. You should never change
commands that have already been run. New DDL will be (manually) run against the
production database as part of deployment.


### Example data

The gratipay database created in the last step is empty. To populate it with
some fake data, so that more of the site is functional, run this command:

    $ make data


API
===

The Gratipay API is comprised of these six endpoints:

**[/about/charts.json](https://gratipay.com/about/charts.json)**
([source](https://github.com/gratipay/gratipay.com/tree/master/www/about/charts.json.spt))&mdash;<i>public</i>&mdash;Returns
an array of objects, one per week, showing aggregate numbers over time. The
[stats](https://gratipay.com/about/stats) page uses this.

**[/about/paydays.json](https://gratipay.com/about/paydays.json)**
([source](https://github.com/gratipay/gratipay.com/tree/master/www/about/paydays.json.spt))&mdash;<i>public</i>&mdash;Returns
an array of objects, one per week, showing aggregate numbers over time. The old
charts page used to use this.

**[/about/stats.json](https://gratipay.com/about/stats.json)**
([source](https://github.com/gratipay/gratipay.com/tree/master/www/about/stats.spt))&mdash;<i>public</i>&mdash;Returns
an object giving a point-in-time snapshot of Gratipay. The
[stats](https://gratipay.com/about/stats.html) page displays the same info.

**/`%username`/charts.json**
([example](https://gratipay.com/Gratipay/charts.json),
[source](https://github.com/gratipay/gratipay.com/tree/master/www/%25username/charts.json.spt))&mdash;<i>public</i>&mdash;Returns
an array of objects, one per week, showing aggregate numbers over time for the
given user.

**/`%username`/public.json**
([example](https://gratipay.com/Gratipay/public.json),
[source](https://github.com/gratipay/gratipay.com/tree/master/www/%25username/public.json.spt))&mdash;<i>public</i>&mdash;Returns an object with these keys:

  - "receiving"&mdash;an estimate of the amount the given participant will
    receive this week

  - "my_tip"&mdash;logged-in user's tip to the Gratipay participant in
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
          - `http://www.openstreetmap.org/user/%openstreetmap_username`


**/`%username`/tips.json**
([source](https://github.com/gratipay/gratipay.com/tree/master/www/%25username/tips.json.spt))&mdash;<i>private</i>&mdash;Responds
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
Additionally, currently, the only supported platform is 'gratipay' ('gittip'
still works for backwards-compatibility).

This endpoint requires authentication. Look for your user ID and API key on your
[account page](https://gratipay.com/about/me/account), and pass them using basic
auth. E.g.:

```
curl https://gratipay.com/foobar/tips.json \
    -u $userid:$api_key \
    -X POST \
    -d'[{"username":"bazbuz", "platform":"gratipay", "amount": "1.00"}]' \
    -H"Content-Type: application/json"
```

API Implementations
-------------------

Below are some projects that use the Gratipay APIs, that can serve as inspiration
for your project!

### Renamed to Gratipay

 - [Ruby: gratitude](https://github.com/JohnKellyFerguson/gratitude): A simple 
   ruby wrapper for the Gratipay API.

 - [php-curl-class](https://github.com/php-curl-class/php-curl-class/blob/master/examples/gratipay_send_tip.php): A php class to tip using the Gratipay API.

 - [gratipay-twisted](https://github.com/TigerND/gratipay-twisted): Gratipay client
   for the Twisted framework


### Still Using Gittip

These probably still work, but are using our [old name](https://medium.com/gratipay-blog/gratitude-gratipay-ef24ad5e41f9):

 - [Drupal: Gittip](https://drupal.org/project/gittip): Includes a Gittip
   giving field type to let you implement the Khan academy model for users on
   your Drupal site. ([ticket](https://www.drupal.org/node/2332131))

 - [Node.js: Node-Gittip](https://npmjs.org/package/gittip) (also see [Khan
   Academy's setup](http://ejohn.org/blog/gittip-at-khan-academy/)) ([ticket](https://github.com/KevinTCoughlin/node-gittip/issues/1))

 - [WordPress: WP-Gittip](https://github.com/daankortenbach/WP-Gittip) ([ticket](https://github.com/daankortenbach/WP-Gittip/issues/2))

 - [hubot-gittip](https://github.com/myplanetdigital/hubot-gittip): A Hubot
   script for interacting with a shared Gratipay account. ([ticket](https://github.com/myplanetdigital/hubot-gittip/issues/6))

 - [gittip-collab](https://github.com/engineyard/gittip-collab): A Khan-style
   tool for managing a Gittip account as a team. ([ticket](https://github.com/engineyard/gittip-collab/issues/1))

 - [WWW::Gittip](https://metacpan.org/pod/WWW::Gittip): A Perl module
   implementing the Gittip API more or less ([ticket](https://rt.cpan.org/Public/Bug/Display.html?id=101103))


Glossary
========

**Account Elsewhere** - An entity's registration on a platform other than
Gratipay (e.g., Twitter).

**Entity** - An entity.

**Participant** - An entity registered with Gratipay.

**User** - A person using the Gratipay website. Can be authenticated or
anonymous. If authenticated, the user is guaranteed to also be a participant.

License
========

Gratipay is dedicated to public domain. See the text of [CC0 1.0 Universal](http://creativecommons.org/publicdomain/zero/1.0/) dedication in [COPYING](COPYING) here.
