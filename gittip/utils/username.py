from psycopg2 import IntegrityError
import random

def gen_random_usernames():
    """Yield up to 100 random 12-hex-digit unicodes.

    We raise :py:exc:`StopIteration` after 100 usernames as a safety
    precaution.

    """
    seatbelt = 0
    while 1:
        yield hex(int(random.random() * 16**12))[2:].zfill(12).decode('ASCII')
        seatbelt += 1
        if seatbelt > 100:
            raise StopIteration


def reserve_a_random_username(txn):
    """Reserve a random username.

    :param txn: a :py:class:`psycopg2.cursor` managed as a :py:mod:`postgres`
        transaction
    :database: one ``INSERT`` on average
    :returns: a 12-hex-digit unicode
    :raises: :py:class:`StopIteration` if no acceptable username is found
        within 100 attempts

    The returned value is guaranteed to have been reserved in the database.

    """
    for username in gen_random_usernames():
        try:
            txn.execute( "INSERT INTO participants (username, username_lower) "
                         "VALUES (%s, %s)"
                       , (username, username.lower())
                        )
        except IntegrityError:  # Collision, try again with another value.
            pass
        else:
            break

    return username


class ProblemChangingUsername(Exception):
    def __str__(self):
        return self.msg.format(self.args[0])
