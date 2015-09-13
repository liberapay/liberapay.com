[Liberapay](http://liberapay.com) is a recurrent donations platform, trying to bring back the original spirit of Gittip that [Gratipay](http://gratipay.com) has [strayed away from](https://medium.com/gratipay-blog/gratipay-2-0-2453d3c53077).


## Contributing to the translations

[![We use Weblate for translations](https://hosted.weblate.org/widgets/liberapay/-/287x66-white.png)](https://hosted.weblate.org/engage/liberapay/?utm_source=widget)


## Contributing to the code

### Installation

Firstly, make sure you have the following dependencies installed:

- python 2.7 (a pull request to port to python 3 is very much welcome)
- virtualenv
- postgresql
- make

Then run:

    make env

Now you'll need to create two postgres databases, here's the simplest way of doing it:

    sudo -u postgres createuser --superuser $USER
    createdb liberapay
    createdb liberapay_tests

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

You can create some fake users to make it look more like the real site:

    make data

### Modifying the database schema

The DB schema is in `sql/schema.sql`, but don't modify that file directly,
instead put the changes in `sql/branch.sql`. During deployment that script will
be run on the production DB and the changes will be merged into `sql/schema.sql`.

That process is semi-automated by `release.sh`.

### Testing [![Build Status](https://travis-ci.org/liberapay/liberapay.com.svg)](https://travis-ci.org/liberapay/liberapay.com)

The easiest way to run the test suite is:

    make test

That recreates the test DB's schema and runs all the tests. To speed things up
you can also use the following commands:

- `make pytest` only runs the python tests without recreating the test DB
- `make pytest-re` does the same but only runs the tests that failed in the previous run

### Help

Need some help? [Open an issue](https://github.com/liberapay/liberapay.com/issues/new) or come ask your question in the IRC channel #liberapay on [Freenode](http://webchat.freenode.net/).


## License

[CC0 Public Domain Dedication](http://creativecommons.org/publicdomain/zero/1.0/)
