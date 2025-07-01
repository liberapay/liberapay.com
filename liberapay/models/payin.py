from functools import cached_property

from postgres.orm import Model


class Payin(Model):
    typname = "payins"

    @cached_property
    def recipient_names(self):
        return self.db.all("""
            SELECT DISTINCT tippee_p.username
              FROM payin_transfers pt
              JOIN participants tippee_p ON tippee_p.id = coalesce(pt.team, pt.recipient)
             WHERE pt.payer = %s
               AND pt.payin = %s
          ORDER BY tippee_p.username
        """, (self.payer, self.id))
