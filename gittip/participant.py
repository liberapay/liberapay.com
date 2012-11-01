from gittip import db


class Participant(object):

    def __init__(self, participant_id):
        self.participant_id = participant_id

    def suspend_payin(self):
        db.execute( "UPDATE participants SET payin_suspended=true WHERE id=%s"
                  , (self.participant_id,)
                   )

    def unsuspend_payin(self):
        db.execute( "UPDATE participants SET payin_suspended=false WHERE id=%s"
                  , (self.participant_id,)
                   )
