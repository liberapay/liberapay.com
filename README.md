# Liberapay

[![Build Status](https://travis-ci.org/liberapay/liberapay.com.svg?branch=master)](https://travis-ci.org/liberapay/liberapay.com)
[![Weblate](https://hosted.weblate.org/widgets/liberapay/-/shields-badge.svg)](https://hosted.weblate.org/engage/liberapay/?utm_source=widget)
[![Gitter](https://badges.gitter.im/liberapay/salon.svg)](https://gitter.im/liberapay/salon?utm_source=badge)
[![Income](https://img.shields.io/liberapay/receives/Liberapay.svg)](https://liberapay.com/Liberapay)
[![Donate](https://liberapay.com/assets/widgets/donate.svg)](https://liberapay.com/liberapay/donate)

[Liberapay](http://liberapay.com) is a recurrent donations platform. We help you fund the creators and projects you appreciate.

Note: This webapp is not self-hostable.

## Table of Contents

- [Contact](#contact)
- [Contributing to the translations](#contributing-to-the-translations)
- [Contributing to the code](#contributing-to-the-code)
  - [Introduction](#introduction)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running](#running)
    - [Payday](#payday)
  - [SQL](#sql)
  - [CSS and JavaScript](#css-and-javascript)
  - [Testing](#testing)
    - [Updating test fixtures](#updating-test-fixtures)
    - [Speeding up the tests](#speeding-up-the-tests)
  - [Tinkering with payments](#tinkering-with-payments)
  - [Modifying python dependencies](#modifying-python-dependencies)
  - [Processing personal data](#processing-personal-data)
  - [Deploying the app](#deploying-the-app)
  - [Setting up a development environment using Docker](#setting-up-a-development-environment-using-docker)
- [License](#license)

## Contact

You want to chat? [Join us on Gitter](https://gitter.im/liberapay/salon). (If you use IRC, [Gitter has a gateway](https://irc.gitter.im/), and we're also in the #liberapay channel on Freenode.)

Alternatively you can post a message in [our GitHub salon](https://github.com/liberapay/salon).


## Contributing to the translations

You can help translate Liberapay [via Weblate](https://hosted.weblate.org/engage/liberapay/). Current status:

[![global translation status](https://hosted.weblate.org/widgets/liberapay/-/287x66-white.png)](https://hosted.weblate.org/engage/liberapay/?utm_source=widget)

[![translation status by language](https://hosted.weblate.org/widgets/liberapay/-/multi-auto.svg)](https://hosted.weblate.org/projects/liberapay/core/?utm_source=widget)

If you have questions about translating Liberapay, you can ask them [in the salon](https://github.com/liberapay/salon/labels/i18n).


## Contributing to the code

### Introduction

Liberapay was originally forked from [Gratipay](https://github.com/gratipay/gratipay.com) and inherited its web micro-framework [Pando](https://github.com/AspenWeb/pando.py) (*né* Aspen), which is based on filesystem routing and [simplates](http://simplates.org/). Don't worry, it's quite simple. For example to make Liberapay return a `Hello $user, your id is $userid` message for requests to the URL `/$user/hello`, you only need to create the file `www/%username/hello.spt` with this inside:

```
from liberapay.utils import get_participant
[---]
participant = get_participant(state)
[---] text/html
{{ _("Hello {0}, your id is {1}", request.path['username'], participant.id) }}
```

As illustrated by the last line our default template engine is [Jinja](http://jinja.pocoo.org/).

The `_` function attempts to translate the message into the user's language and escapes the variables properly (it knows that it's generating a message for an HTML page).

The python code inside simplates is only for request-specific logic, common backend code is in the `liberapay/` directory.

### Installation

Firstly, make sure you have the following dependencies installed:

- python ≥ 3.6
  - including the C headers of python and libffi, which are packaged separately in many Linux distributions
- postgresql 9.6 (see [the official download & install docs](https://www.postgresql.org/download/))
- make

Then run:

    make env

Now you need to give yourself superuser postgres powers (if it hasn't been done already), and create two databases:

    su postgres -c "createuser --superuser $(whoami)"

    createdb liberapay
    createdb liberapay_tests

If you need a deeper understanding take a look at the [Database Roles](https://www.postgresql.org/docs/9.4/static/user-manag.html) and [Managing Databases](https://www.postgresql.org/docs/9.4/static/managing-databases.html) sections of PostgreSQL's documentation.

Then you can set up the DB:

    make schema

### Configuration

Environment variables are used for configuration, the default values are in
`defaults.env` and `tests/test.env`. You can override them in
`local.env` and `tests/local.env` respectively.

### Running

Once you've installed everything and set up the database, you can run the app:

    make run

It should now be accessible at [http://localhost:8339/](http://localhost:8339/).

By default there are no users. You can create accounts like you would on the real website, and if you want you can also create a bunch of fake users (but they're not great):

    make data

To grant admin permissions to an account, modify the database like so:

    psql liberapay -c "update participants set privileges = 1 where username = 'account-username'"

#### Payday

To run a local payday open [http://localhost:8339/admin/payday](http://localhost:8339/admin/payday) and click the "Run payday" button. You can add `OVERRIDE_PAYDAY_CHECKS=yes` in the `local.env` file to disable the safety checks that prevent running payday at the wrong time.

### SQL

The python code interacts with the database by sending raw SQL queries through
the [postgres.py](https://postgres-py.readthedocs.org/en/latest/) library.

The [official PostgreSQL documentation](https://www.postgresql.org/docs/9.6/static/index.html) is your friend when dealing with SQL, especially the sections "[The SQL Language](https://www.postgresql.org/docs/9.6/static/sql.html)" and "[SQL Commands](https://www.postgresql.org/docs/9.6/static/sql-commands.html)".

The DB schema is in `sql/schema.sql`, but don't modify that file directly,
instead put the changes in `sql/branch.sql`. During deployment that script will
be run on the production DB and the changes will be merged into `sql/schema.sql`.
That process is semi-automated by `release.sh`.

### CSS and JavaScript

For our styles we use [SASS](http://sass-lang.com/) and [Bootstrap 3](https://getbootstrap.com/). Stylesheets are in the `style/` directory and our JavaScript code is in `js/`. Our policy for both is to have as little as possible of them: the website should be almost entirely usable without JS, and our CSS should leverage Bootstrap as much as possible instead of containing lots of custom rules that would become a burden to maintain.

We compile Bootstrap ourselves from the SASS source in the `style/bootstrap/`
directory. We do that to be able to easily customize it by changing values in
`style/variables.scss`. Modifying the files in `style/bootstrap/` is probably
not a good idea.

### Testing

The easiest way to run the test suite is:

    make test

That recreates the test DB's schema and runs all the tests. To speed things up
you can also use the following commands:

- `make pytest` only runs the python tests without recreating the test DB
- `make pytest-re` does the same but only runs the tests that failed in the previous run

#### Updating test fixtures

Some of our tests include interactions with external services. In order to speed up those tests we record the requests and responses automatically using [vcr](https://pypi.python.org/pypi/vcrpy). The records are in the `tests/py/fixtures` directory, one per test class.

If you add or modify interactions with external services, then the tests will fail, because VCR will not find the new or modified request in the records, and will refuse to record the new request by default (see [Record Modes](https://vcrpy.readthedocs.io/en/latest/usage.html#record-modes) for more information). When that happens you can either switch the record mode from `once` to `new_episodes` (in `liberapay/testing/vcr.py`) or delete the obsolete fixture files.

If the new interactions are with MangoPay you have to delete the file `tests/py/fixtures/MangopayOAuth.yml`, otherwise you'll be using an expired authentication token and the requests will be rejected.

#### Speeding up the tests

PostgreSQL is designed to prevent data loss, so by default it does a lot of synchronous disk writes. To reduce the number of those blocking writes our `recreate-schema.sh` script automatically switches the `synchronous_commit` option to `off` for the test database, however this doesn't completely disable syncing. If your PostgreSQL instance only contains data that you can afford to lose, then you can speed things up further by setting `fsync` to `off` in the server's configuration file (`postgresql.conf`).

### Tinkering with payments

Liberapay was built on top of [MangoPay](https://www.mangopay.com/) for payments, however they [kicked us out](https://medium.com/liberapay-blog/liberapay-is-in-trouble-b58b40714d82) so we've shifted to integrating with multiple payment processors. We currently support [Stripe](https://stripe.com/docs) and [PayPal](https://developer.paypal.com/docs/). Support for Mangopay hasn't been completely removed yet.

### Modifying python dependencies

All new dependencies need to be audited to check that they don't contain malicious code or security vulnerabilities.

We use [pip's Hash-Checking Mode](https://pip.pypa.io/en/stable/reference/pip_install/#hash-checking-mode) to protect ourselves from dependency tampering. Thus when adding or upgrading a dependency the new hashes need to computed and put in the requirements file. For that you can use [hashin](https://github.com/peterbe/hashin):

    pip install hashin
    hashin package==x.y -r requirements_base.txt -p 3.4 -p 3.6
    # note: we have several requirements files, use the right one

If for some reason you need to rehash all requirements, run `make rehash-requirements`.

### Processing personal data

When writing code that handles personal information keep in mind the principles enshrined in the [GDPR](https://en.wikipedia.org/wiki/General_Data_Protection_Regulation).

### Deploying the app

Note: Liberapay cannot be self-hosted, this section is only meant to document how we deploy new versions.

Liberapay is currently hosted on [AWS](https://aws.amazon.com/) (Ireland).

To deploy the app simply run `release.sh`, it'll guide you through it. Of course you need to be given access first.

### Setting up a development environment using Docker

If you don't want to install directly dependencies on your machine, you can spin up a development environment easily, assuming you have [Docker](https://docs.docker.com/engine/installation/) and [docker-compose](https://docs.docker.com/compose/install/) installed:

    # build the local container
    docker-compose build

    # initialize the database
    docker-compose run web bash recreate-schema.sh

    # populate the database with fake data
    docker-compose run web python -m liberapay.utils.fake_data

    # launch the database and the web server
    # the application should be available on http://localhost:8339
    docker-compose up

You can also run tests in the Docker environment:

    docker-compose -f docker/tests.yml run tests

All arguments are passed to the underlying `py.test` command, so you can use `-x` for failing fast or `--ff` to retry failed tests first:

    docker-compose -f docker/tests.yml run tests -x --ff

## License

[CC0 Public Domain Dedication](http://creativecommons.org/publicdomain/zero/1.0/) (See [this discussion](https://github.com/liberapay/liberapay.com/issues/564) for details.)
