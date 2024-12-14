from datetime import timedelta
from functools import cached_property

from postgres.orm import Model


class Tip(Model):

    typname = "tips"

    def __init__(self, values=(), **extra_values):
        super().__init__(values)
        self.__dict__.update(extra_values)

    def __contains__(self, key):
        return key in self.__dict__

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    __setattr__ = object.__setattr__

    def __setitem__(self, key, value):
        try:
            object.__setattr__(self, key, value)
        except AttributeError:
            raise KeyError(key)

    def __repr__(self):
        try:
            return f'<Tip id={self.id!r} tipper={self.tipper!r} tippee={self.tippee!r} amount={self.amount!r}>'
        except AttributeError:
            return f'<Tip {self.__dict__!r}>'

    def _asdict(self):
        # For compatibility with namedtuple classes
        return self.__dict__.copy()

    def compute_renewal_due_date(self, next_payday, cursor=None):
        if not cursor:
            cursor = self.db
        weeks_left = self.weeks_left
        if weeks_left is None:
            return
        if weeks_left == 0:
            last_transfer_date = cursor.one("""
                SELECT tr.timestamp::date
                  FROM transfers tr
                 WHERE tr.tipper = %s
                   AND coalesce(tr.team, tr.tippee) = %s
                   AND tr.context IN ('tip', 'take')
              ORDER BY tr.timestamp DESC
                 LIMIT 1
            """, (self.tipper, self.tippee)) or cursor.one("""
                SELECT pt.ctime::date
                  FROM payin_transfers pt
                 WHERE pt.payer = %s
                   AND coalesce(pt.team, pt.recipient) = %s
                   AND pt.context IN ('personal-donation', 'team-donation')
              ORDER BY pt.ctime DESC
                 LIMIT 1
            """, (self.tipper, self.tippee))
            if last_transfer_date:
                return last_transfer_date + timedelta(weeks=1)
            else:
                return self.mtime.date()
        else:
            return next_payday + timedelta(weeks=weeks_left)

    def for_json(self):
        return {k: v for k, v in self.__dict__.items() if not isinstance(v, self.db.Participant)}

    @property
    def is_pledge(self):
        return self.tippee_p.payment_providers == 0

    @cached_property
    def pending_payins_count(self):
        return self.db.one("""
            SELECT count(DISTINCT pi.id)
              FROM payin_transfers pt
              JOIN payins pi ON pi.id = pt.payin
             WHERE pt.payer = %(tipper)s
               AND coalesce(pt.team, pt.recipient) = %(tippee)s
               AND (pt.status IN ('awaiting_review', 'pending') OR
                    pi.status IN ('awaiting_review', 'pending'))
        """, dict(tipper=self.tipper, tippee=self.tippee))

    @cached_property
    def tippee_p(self):
        return self.db.one("SELECT p FROM participants p WHERE p.id = %s", (self.tippee,))

    @cached_property
    def tipper_p(self):
        return self.db.one("SELECT p FROM participants p WHERE p.id = %s", (self.tipper,))

    @cached_property
    def weeks_left(self):
        if self.paid_in_advance is None:
            return
        return int(self.paid_in_advance // self.amount)
