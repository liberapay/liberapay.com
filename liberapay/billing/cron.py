from ..cron import logger
from ..website import website

def generate_profile_description_missing_notifications():
    """Send a notification to users without a profile description to add one
    if they begin to receive payments. #2013"""

    tippees_without_description = website.db.all("""
        SELECT DISTINCT tippee FROM transfers t
        WHERE status = 'succeeded'
        AND t.timestamp >= (current_timestamp - interval '180 days')
        AND t.context IN ('tip', 'take', 'partial-take')
        AND t.tippee NOT IN (
            SELECT DISTINCT participant
            FROM statements
        )
        AND t.tippee NOT IN (
            SELECT DISTINCT participant FROM notifications n
            WHERE n.event = 'profile_description_missing'
            AND ts >= (current_timestamp - interval '180 days')
        )
    """)

    for tippee_id in tippees_without_description:
        p = website.db.Participant.from_id(tippee_id)
        p.notify('profile_description_missing', force_email=True)
        logger.info("Sent update_profile notification to user %s." % p.id)
