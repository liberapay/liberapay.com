# Liberapay

[![Weblate](https://hosted.weblate.org/widgets/liberapay/-/shields-badge.svg)](https://hosted.weblate.org/engage/liberapay/?utm_source=widget)
[![Open Source Helpers](https://www.codetriage.com/liberapay/liberapay.com/badges/users.svg)](https://www.codetriage.com/liberapay/liberapay.com)
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
- [License](#license)

## Contact

Want to chat? [Join us on Gitter](https://gitter.im/liberapay/salon).

Alternatively you can post a message in [our GitHub salon](https://github.com/liberapay/salon).


## Contributing to the translations

You can help translate Liberapay [via Weblate](https://hosted.weblate.org/engage/liberapay/). Current status:

[![global translation status](https://hosted.weblate.org/widgets/liberapay/-/core/287x66-white.png)](https://hosted.weblate.org/engage/liberapay/?utm_source=widget)

[![translation status by language](https://hosted.weblate.org/widgets/liberapay/-/core/multi-auto.svg)](https://hosted.weblate.org/projects/liberapay/core/?utm_source=widget)

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

Make sure you have the following dependencies installed first:

- python ≥ 3.12
  - including the C headers of python and libffi, which are packaged separately in many Linux distributions
- postgresql 16 (see [the official download & install docs](https://www.postgresql.org/download/))
- make

Then run:

    make env

Now you need to give yourself superuser postgres powers (if it hasn't been done already). One of these commands should work:

    sudo -u postgres -c "createuser --superuser $(whoami)"
    su -c "su postgres -c 'createuser --superuser $(whoami)'"

Then create two databases:

    createdb liberapay
    createdb liberapay_tests

If you need a deeper understanding, take a look at the [Database Roles](https://www.postgresql.org/docs/9.4/static/user-manag.html) and [Managing Databases](https://www.postgresql.org/docs/9.4/static/managing-databases.html) sections of PostgreSQL's documentation.

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

There are no users provided by default. You can create accounts as you would on the real website, and if you want you can also create a bunch of fake users (but they're not great):

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

For our styles we use [SASS](http://sass-lang.com/) and [Bootstrap 3](https://getbootstrap.com/). Stylesheets are in the `style/` directory and our JavaScript code is in `js/`. Our policy for both is to include as little as possible of them: the website should be almost entirely usable without JS, and our CSS should leverage Bootstrap as much as possible instead of containing lots of custom rules that would become a burden to maintain.

We compile Bootstrap ourselves from the SASS source in the `style/bootstrap/`
directory. We do that to be able to easily customize it by changing values in
`style/variables.scss`. Modifying the files in `style/bootstrap/` is probably
a bad idea.

### Icons

For user interface icons we use [Bootstrap Icons](https://icons.getbootstrap.com/). An icon can be included in a page by calling the `icon` macro from `templates/macros/icons.html`, e.g. `{{ icon('liberapay') }}`. The icons are stored in the `www/assets/icons.svg` file. To add a new icon in that file, the root `<svg>` element of the icon being added must be turned into a `<symbol>` element, preserving only its `viewBox` attribute and adding an `id` attribute.

If you don't find any icon in Bootstrap Icons that fits your use case, you can try to search online catalogs like [Flaticon](https://www.flaticon.com/search?type=uicon), [Icons8](https://icons8.com/icons), [Pictogrammers](https://pictogrammers.com/), [SVG Repo](https://www.svgrepo.com/) and [The Noun Project](https://thenounproject.com/). For brand icons, [Simple Icons](https://simpleicons.org/) is a good resource.

### Testing

The easiest way to run the test suite is:

    make test

This recreates the test DB's schema and runs all the tests. To speed things up
you can also use the following commands:

- `make pytest` only runs the python tests without recreating the test DB
- `make pytest-re` only runs the tests that failed previously

#### Updating test fixtures

Some of our tests include interactions with external services. In order to speed up those tests we record the requests and responses automatically using [vcr](https://pypi.python.org/pypi/vcrpy). The records are in the `tests/py/fixtures` directory, one per test class.

If you add or modify interactions with external services, then the tests will fail, because VCR will not find the new or modified request in the records, and will refuse to record the new request by default (see [Record Modes](https://vcrpy.readthedocs.io/en/latest/usage.html#record-modes) for more information). When that happens you can either add `VCR=new_episodes` to your test command (e.g. `make pytest VCR=new_episodes`) or delete the obsolete fixture files (e.g. `rm tests/py/fixtures/TestPayinsStripe.yml`).

If you're testing an API which uses idempotency keys (for example Stripe's API), then some requests will fail if they're no longer exactly identical. In that case, increase the value of the test class' `offset` attribute so that different idempotency keys will be used.

#### Speeding up the tests

PostgreSQL is designed to prevent data loss, so it does a lot of synchronous disk writes by default. To reduce the number of those blocking writes, our `recreate-schema.sh` script automatically switches the `synchronous_commit` option to `off` for the test database, however this doesn't completely disable syncing. If your PostgreSQL instance only contains data that you can afford to lose, then you can speed things up further by setting `fsync` to `off`, `wal_level` to `minimal` and `max_wal_senders` to `0` in the server's configuration file (`postgresql.conf`).

### Tinkering with payments

Liberapay currently supports two payment processors: [Stripe](https://stripe.com/docs) and [PayPal](https://developer.paypal.com/).

#### Testing Stripe webhooks

You can forward Stripe's callbacks to your local Liberapay instance by running `make stripe-bridge`. The [stripe-cli](https://github.com/stripe/stripe-cli) program has to be installed for this to work.

### Modifying python dependencies

All new dependencies need to be audited to check that they don't contain malicious code or security vulnerabilities.

We use [pip's Hash-Checking Mode](https://pip.pypa.io/en/stable/topics/secure-installs/#hash-checking-mode) to protect ourselves from dependency tampering. Thus, when adding or upgrading a dependency the new hashes need to be computed and put in the requirements file. For that you can use [hashin](https://github.com/peterbe/hashin):

    pip install hashin
    hashin package==x.y -r requirements_base.txt

If for some reason you need to rehash all requirements, run `make rehash-requirements`.

To upgrade all the dependencies in the requirements file, run `hashin -u -r requirements_base.txt`. You may have to run extra `hashin` commands if new subdependencies are missing.

The testing dependencies in `requirements_tests.txt` don't follow these rules because they're not installed in production. It's up to you to isolate your development environment from the rest of your system in order to protect it from possible vulnerabilities in the testing dependencies.

### Processing personal data

When writing code that handles personal information, keep in mind the principles enshrined in the [GDPR](https://en.wikipedia.org/wiki/General_Data_Protection_Regulation).

### Deploying the app

Note: Liberapay cannot be self-hosted, this section is only meant to document how we deploy new versions.

Liberapay is currently hosted on [AWS](https://aws.amazon.com/) (Ireland).

To deploy the app simply run `release.sh`, it'll guide you through it. Of course you need to be given access first.

## License

[CC0 Public Domain Dedication](https://creativecommons.org/publicdomain/zero/1.0/) (See [this discussion](https://github.com/liberapay/liberapay.com/issues/564) for details.)
