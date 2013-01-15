from sqlalchemy.dialects.postgresql.hstore import HSTORE
from sqlalchemy.schema import Column, UniqueConstraint, ForeignKey
from sqlalchemy.types import Integer, Text, Boolean

from gittip.orm import db

class Elsewhere(db.Model):
    __tablename__ = 'elsewhere'
    __table_args__ = (
        UniqueConstraint('platform', 'participant_id',
                         name='elsewhere_platform_participant_id_key'),
        UniqueConstraint('platform', 'user_id',
                         name='elsewhere_platform_user_id_key')
    )

    id = Column(Integer, nullable=False, primary_key=True)
    platform = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)
    user_info = Column(HSTORE)
    is_locked = Column(Boolean, default=False, nullable=False)
    participant_id = Column(Text, ForeignKey("participants.id"), nullable=False)

    def resolve_unclaimed(self):
        if self.platform == 'github':
            out = '/on/github/%s/' % self.user_info['login']
        elif self.platform == 'twitter':
            out = '/on/twitter/%s/' % self.user_info['screen_name']
        else:
            out = None
        return out