from __future__ import unicode_literals

from sqlalchemy import Table

from gittip.orm import metadata


participants = Table('participants', metadata, autoload=True)
