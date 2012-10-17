"""This is a demonstration script for Gittip's test suite.
"""

# Layout
# ======
# The Gittip test suite lives at tests/test_*.py. The tests/ directory is not a
# Python package (there is no __init__.py). Think of it as holding test scripts
# to be run via nosetest (maybe py.test would work too?). Helpers are defined
# in the gittip.testing module.

from gittip import testing


# Basic Pattern
# =============

# First, import something from the gittip library. Here I'm defining a function
# inline for demonstration purposes.

def greet():
    return "Greetings, program!"


# Then, write a test case. Here's what a canonical test case in the Gittip test
# suite looks like:

def test_greet_greets_programs():
    expected = "Greetings, program!"
    actual = greet()
    assert actual == expected, actual


# The name of the test case should be a sentence, with a subject and a
# predicate. The subject should be the thing under test, and the predicate
# should state the expected behavior we're testing for.

def test_greet_still_greets_programs():

    # More complex tests will start with some setup. Here in this test we don't
    # have any. The last three lines of each test case look like the following.

    # Ask questions first, shoot later: our expectation always preceeds the
    # performance of the test.
    expected = "Greetings, program!"

    # Perform the test, storing the result in actual.
    actual = greet()

    # Compare reality with our expectation, and, if they don't match, inform
    # the viewer of reality.
    assert actual == expected, actual


# Context Managers
# ================
# Gittip's test suite uses context managers to manage testing state instead of
# test classes with setup/teardown methods. The reason is to make the test
# suite flatter and easier to follow, and to keep a tight coupling between test
# fixture and test cases. We want to avoid bloated super-fixtures.

def test_inserting_inserts():

    # Gittip's fundamental context manager for testing is gittip.testing.load.
    # It's called that because its primary function is to load data into the
    # database. When the context manager exits, the database is wiped.

    with testing.load() as context:

        # The context object gives you access to the database. The db attribute
        # here is the usual PostgresManager that is used throughout Gittip.

        context.db.execute("INSERT INTO participants VALUES ('foo')")


        # There's a dump method on context that gives you all the data in the
        # database, as a mapping of table names to mappings of id to row dict.

        actual = context.dump()


        # The context.diff method gives you a diff of the state of the database
        # since you entered the context. With compact=True it returns a mapping
        # of the names of tables that have changed, to a list of ints showing
        # the number of rows that have been inserted, updated, and deleted,
        # respectively.

        actual = context.diff(compact=True)


        # If the expectation can be stated succinctly, it's acceptable to
        # inline it in the assertion, rather than defining it separately.

        assert actual == {"participants": [1,0,0]}, actual

def test_something_changes_something():

    # The testing.load callable takes a data definition as positional
    # arguments. {str,unicode} is interpreted as a table name, and {dict,list,
    # tuple} is interpreted as a row of data to be inserted into the most
    # recently named table. Generally you'll end up defining "data" and then
    # calling testing.load(*data), as it won't fit on one line.

    with testing.load("participants", ("foo",)) as context:
        context.db.execute("UPDATE participants SET statement='BLAM!!!' "
                           "WHERE id='foo'")

        # Calling context.diff without compact=True gives you a mapping of the
        # names of tables that have changed to a mapping with keys 'inserts',
        # 'updates', and 'deletes'. The values for inserts and deletes are
        # lists of row dicts containing the new and old data, respectively. The
        # value for updates is a list of dicts containing only the data that
        # has changed (and the primary key).

        expected = {"id": "foo", "statement": "BLAM!!!"}
        actual = context.diff()['participants']['updates'][0]
        assert actual == expected, actual


# Wrappers
# --------
# Write wrappers for test cases that want slightly varying but similar state.
# Start by writing them in the same file as the test cases. If the wrappers
# turn out to be useful in multiple test scripts then we'll move them into
# gittip.testing.

def let_them_eat_cake(): # For demonstration; this would be imported.
    """Simulate the gittip application doing something.
    """
    import gittip
    rec = gittip.db.fetchone('SELECT id FROM participants')
    return "{id} eats cake.".format(**rec)


def participant(participant_id):
    """Wrap testing.load to install a participant.
    """
    context = testing.load("participants", (participant_id,))
    return context


def test_foo_eats_cake():
    with participant("foo"):
        actual = let_them_eat_cake()
        assert actual == "foo eats cake.", actual

def test_bar_eats_cake():
    with participant("bar"):
        actual = let_them_eat_cake()
        assert actual == "bar eats cake.", actual

# NB: There is one line between related test cases instead of two, as a way to
# group them together.
