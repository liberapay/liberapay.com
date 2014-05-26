# Welcome to Gittip [<img height="26px" src="www/assets/%25version/gittip.opengraph.png"/>](https://www.gittip.com/)

[![Build Status](http://img.shields.io/travis/gittip/www.gittip.com/master.svg)](https://travis-ci.org/gittip/www.gittip.com)
[![HuBoard badge](http://img.shields.io/badge/Hu-Board-7965cc.svg)](https://huboard.com/gittip/www.gittip.com)

Gittip is a weekly gift exchange, helping to create a culture of generosity.
If you'd like to learn more, check out <https://gittip.com/about>.
If you'd like to contribute to Gittip, the best first reference is <https://gittip.com/for/contributors>.

Quick Start
===========

Vagrant
-------

Given VirtualBox 4.3 and Vagrant 1.5.4:

```
$ vagrant up
```

[Read more](#vagrant-1).


Docker
-------

Given some version(?) of Docker:

```
$ docker build -t gittip .
$ docker run -p 8537:8537 gittip
```

[Read more](#docker-1).


Local 
-----

Given Python 2.7, Postgres 9.3, and a C/make toolchain:

```
$ git clone git@github.com:gittip/www.gittip.com.git
$ cd www.gittip.com
$ sudo -u postgres createuser --superuser $USER
$ createdb gittip
$ make schema data
$ make run
```

And/or:

```
$ make test
```


Table of Contents
=================

 - [Installation](#installation)
  - [Dependencies](#dependencies)
  - [Building](#building)
  - [Launching](#launching)
  - [Vagrant](#vagrant)
  - [Docker](#docker)
  - [Help!](#help)
 - [Configuration](https://github.com/gittip/www.gittip.com/wiki/Configuration)
 - [Modifying CSS](#modifying-css)
 - [Testing](#testing-)
 - [Setting up a Database](#local-database-setup)
 - [API](#api)
  - [Implementations](#api-implementations)
 - [Glossary](#glossary)


Installation
============

Thanks for hacking on Gittip! Be sure to review
[CONTRIBUTING](https://github.com/gittip/www.gittip.com/blob/master/CONTRIBUTING.md#readme)
as well if that's what you're planning to do.


Dependencies
------------

Building `www.gittip.com` requires [Python
2.7](http://python.org/download/releases/2.7.4/), and a gcc/make toolchain.

All Python library dependencies are bundled in the repo (under `vendor/`).

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
`ARCHFLAGS` environment variable and run `make clean env` again (see [this Stack Overflow answer
for more information](http://stackoverflow.com/a/22355874/347246)):

    $ ARCHFLAGS=-Wno-error=unused-command-line-argument-hard-error-in-future make clean env

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

Vagrant
-------
If you have vagrant installed, you can run gittip by running `vagrant up` from the project directory. Please note that if you ever switch between running gittip on your own machine to vagrant or vice versa, you will need to run `make clean`.

If you're using Vagrant for the first time you'll need [Vagrant](http://www.vagrantup.com/) and [VirtualBox](https://www.virtualbox.org/) installed. If you're on Linux you'll need to install `nfs-kernel-server`.

The Vagrantfile will download a custom made image from the internet. If you have a slow internet connection, you can download a local copy of this file, by running:

`curl http://downloads.gittipllc.netdna-cdn.com/gittip.box`

Once downloaded, vagrant will use this local file automatically when you run `vagrant up`. Vagrant is setup to use key based SSH authentication, if you're prompted for a password please use `vagrant`.

**Ubuntu users:** If you experience problems, please see [this
issue](https://github.com/gittip/www.gittip.com/pull/2321#issuecomment-41455169).
As mentioned, you will also need to be wary of projects that are nested
in encrypted directories.

Docker
------------

You can also install/run Gittip with Docker.

Either pull the image from the Docker Index:

```
$ docker pull citruspi/gittip
```

or build it with the included Dockerfile:

```
$ git clone git@github.com:gittip/www.gittip.com.git
$ cd www.gittip.com
$ docker build -t gittip .
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

If you get stuck somewhere along the way, you can find help in the #gittip
channel on [Freenode](http://webchat.freenode.net/) or in the [issue
tracker](/gittip/www.gittip.com/issues/new) here on GitHub.

Thanks for installing Gittip! :smiley:


Modifying CSS
=============

We use SCSS, with files stored in `scss/`. All of the individual files are
combined in `scss/gittip.scss` which itself is compiled by `libsass` in
`www/assets/%version/gittip.css.spt` on each request.

Testing [![Build Status](http://img.shields.io/travis/gittip/www.gittip.com/master.svg)](https://travis-ci.org/gittip/www.gittip.com)
=======

Please write unit tests for all new code and all code you change. Gittip's
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
    [gittip] $ honcho -e defaults.env,local.env run py.test

Local Database Setup
--------------------

For the best development experience, you need a local
installation of [Postgres](http://www.postgresql.org/download/). The best
version of Postgres to use is 9.3.2, because that's what we're using in
production at Heroku. You need at least 9.2, because we depend on being able to
specify a URI to `psql`, and that was added in 9.2.

+ Mac: use Homerew: `brew install postgres`
+ Ubuntu: use Apt: `apt-get install postgresql postgresql-contrib libpq-dev`

To setup the instance for gittip's needs run:

    $ sudo -u postgres createuser --superuser $USER
    $ createdb gittip
    $ createdb gittip-test

You can speed up the test suite when using a regular HDD by running:

    $ psql -q gittip-test -c 'alter database "gittip-test" set synchronous_commit to off'

### Schema

Once Postgres is set up, run:

    $ make schema

Which populates the database named by `DATABASE_URL` with the schema from `schema.sql`.

The `schema.sql` file should be considered append-only. The idea is that it's the log
of DDL that we've run against the production database. You should never change
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
page](https://www.gittip.com/about/me/account), and pass it as the basic auth
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

 - [Ruby: gratitude](https://github.com/JohnKellyFerguson/gratitude): A ruby
   gem that wraps the Gittip API.

 - [WordPress: WP-Gittip](https://github.com/daankortenbach/WP-Gittip)

 - [hubot-gittip](https://github.com/myplanetdigital/hubot-gittip): A Hubot
   script for interacting with a shared Gittip account.

 - [gittip-collab](https://github.com/engineyard/gittip-collab): A Khan-style
   tool for managing a Gittip account as a team.

 - [WWW::Gittip](https://metacpan.org/pod/WWW::Gittip): A Perl module
   implementing the Gittip API more or less

 - [php-curl-class](https://github.com/php-curl-class/php-curl-class/blob/master/examples/gittip_send_tip.php): A php class to tip using the Gittip API.


Glossary
========

**Account Elsewhere** - An entity's registration on a platform other than
Gittip (e.g., Twitter).

**Entity** - An entity.

**Participant** - An entity registered with Gittip.

**User** - A person using the Gittip website. Can be authenticated or
anonymous. If authenticated, the user is guaranteed to also be a participant.
