from cached_property import cached_property
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
               AND (pt.status = 'pending' OR pi.status = 'pending')
        """, dict(tipper=self.tipper, tippee=self.tippee))

    @cached_property
    def tippee_p(self):
        return self.db.one("SELECT p FROM participants p WHERE p.id = %s", (self.tippee,))

    @cached_property
    def tipper_p(self):
        return self.db.one("SELECT p FROM participants p WHERE p.id = %s", (self.tipper,))
