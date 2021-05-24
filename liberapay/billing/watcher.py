from datetime import datetime
import logging

from babel.dates import format_timedelta
from pando.utils import utc

from ..website import website
from .payday import Payday


logger = logging.getLogger('mangopay_watcher')


def parse_ratelimit_header(s):
    return [int(v.strip()) for v in s.split(',')]


def on_response(sender, **kw):
    try:
        headers = kw['result'].headers
        if 'X-RateLimit-Reset' not in headers:
            return
        lists = (
            parse_ratelimit_header(headers['X-RateLimit']),
            parse_ratelimit_header(headers['X-RateLimit-Remaining']),
            parse_ratelimit_header(headers['X-RateLimit-Reset']),
        )
        now = datetime.utcnow().replace(tzinfo=utc)
        next_delay = 0
        i = 0
        for consumed, remaining, reset in zip(*lists):
            i += 1
            limit = consumed + remaining
            percent_remaining = remaining / limit
            if percent_remaining < 0.4:
                # Slow down background requests
                reset = datetime.fromtimestamp(reset, tz=utc)
                reset_delta = reset - now
                next_delay = max(
                    next_delay,
                    reset_delta.total_seconds() / max(remaining, 2)
                )
                if percent_remaining < 0.2:
                    # Log a warning
                    reset_delta = format_timedelta(reset_delta, add_direction=True, locale='en')
                    log_msg = (
                        '{:.1%} of ratelimit #{} has been consumed, '
                        '{} requests remaining, resets {}.'
                    ).format(1 - percent_remaining, i, remaining, reset_delta)
                    logger.warning(log_msg)
        Payday.transfer_delay = next_delay
    except Exception as e:
        website.tell_sentry(e)
