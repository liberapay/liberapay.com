from datetime import timedelta
from enum import Enum, auto
import json
from time import sleep

from aspen.simplates.pagination import parse_specline, split_and_escape
from aspen_jinja2_renderer import SimplateLoader
import boto3
from dns.exception import DNSException
from dns.resolver import Cache, Resolver
from jinja2 import Environment
from pando.utils import utcnow

from liberapay.constants import EMAIL_RE
from liberapay.exceptions import (
    BadEmailAddress, BadEmailDomain, DuplicateNotification, EmailAddressIsBlacklisted,
)
from liberapay.website import website, JINJA_ENV_COMMON


class EmailVerificationResult(Enum):
    FAILED = auto()
    LOGIN_REQUIRED = auto()
    REDUNDANT = auto()
    STYMIED = auto()
    SUCCEEDED = auto()


jinja_env = Environment(**JINJA_ENV_COMMON)
jinja_env_html = Environment(
    autoescape=True, extensions=['jinja2.ext.autoescape'],
    **JINJA_ENV_COMMON
)

def compile_email_spt(fpath):
    """Compile an email simplate.

    Args:
        fpath (str): filesystem path of the simplate to compile

    Returns:
        dict: the compiled pages of the simplate, keyed by content type (the
              first page gets the special key `subject`)
    """
    r = {}
    with open(fpath, 'rb') as f:
        pages = list(split_and_escape(f.read().decode('utf8')))
    for i, page in enumerate(pages, 1):
        tmpl = '\n' * page.offset + page.content
        content_type, renderer = parse_specline(page.header)
        key = 'subject' if i == 1 else content_type
        env = jinja_env_html if content_type == 'text/html' else jinja_env
        r[key] = SimplateLoader(fpath, tmpl).load(env, fpath)
    return r


DNS = Resolver()
DNS.cache = Cache()


def normalize_email_address(email):
    """Normalize an email address.

    Returns:
        str: the normalized email address

    Raises:
        BadEmailAddress: if the address appears to be invalid
        BadEmailDomain: if the domain name is invalid

    """
    # Remove any surrounding whitespace
    email = email.strip()

    # Split the address
    try:
        local_part, domain = email.rsplit('@', 1)
    except ValueError:
        raise BadEmailAddress(email)

    # Lowercase and encode the domain name
    try:
        domain = domain.lower().encode('idna').decode()
    except UnicodeError:
        raise BadEmailDomain(domain)

    # Check the syntax and length of the address
    email = local_part + '@' + domain
    if not EMAIL_RE.match(email) or len(email) > 320:
        # The length limit is from https://tools.ietf.org/html/rfc3696#section-3
        raise BadEmailAddress(email)

    # Check that the domain has at least one MX record
    if website.app_conf.check_email_domains:
        try:
            DNS.query(domain, 'MX')
        except DNSException:
            raise BadEmailDomain(domain)
        except Exception as e:
            website.tell_sentry(e, {})

    return email


def check_email_blacklist(address):
    """Raises `EmailAddressIsBlacklisted` if the given email address is blacklisted.
    """
    r = website.db.one("""
        SELECT reason, ts
          FROM email_blacklist
         WHERE lower(address) = lower(%s)
           AND (ignore_after IS NULL OR ignore_after > current_timestamp)
      ORDER BY ts DESC
         LIMIT 1
    """, (address,))
    if r:
        raise EmailAddressIsBlacklisted(address, r.reason, r.ts)


def handle_email_bounces():
    """Process SES notifications, fetching them from SQS.
    """
    sqs = boto3.resource('sqs', region_name=website.app_conf.ses_region)
    ses_queue = sqs.Queue(website.app_conf.ses_feedback_queue_url)
    while True:
        messages = ses_queue.receive_messages(WaitTimeSeconds=20, MaxNumberOfMessages=10)
        if not messages:
            break
        for msg in messages:
            try:
                _handle_ses_notification(msg)
            except Exception as e:
                website.tell_sentry(e, {})
        sleep(1)


def _handle_ses_notification(msg):
    # Doc: https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html
    data = json.loads(json.loads(msg.body)['Message'])
    notif_type = data['notificationType']
    ignore_after = None
    if notif_type == 'Bounce':
        bounce = data['bounce']
        report_id = bounce['feedbackId']
        recipients = bounce['bouncedRecipients']
        if bounce.get('bounceType') == 'Transient':
            bounce_subtype = bounce.get('bounceSubType')
            if bounce_subtype in ('General', 'MailboxFull'):
                ignore_after = utcnow() + timedelta(days=5)
            else:
                website.warning("unhandled bounce subtype: %r" % bounce_subtype)
    elif notif_type == 'Complaint':
        complaint = data['complaint']
        report_id = complaint['feedbackId']
        recipients = complaint['complainedRecipients']
        complaint_type = complaint['complaintFeedbackType']
        if complaint_type not in ('abuse', 'fraud'):
            # We'll figure out how to deal with that when it happens.
            raise ValueError(complaint_type)
    else:
        raise ValueError(notif_type)
    for recipient in recipients:
        address = recipient['emailAddress']
        if address[-1] == '>':
            address = address[:-1].rsplit('<', 1)[1]
        # Add the address to our blacklist
        r = website.db.one("""
            INSERT INTO email_blacklist
                        (address, reason, ses_data, report_id, ignore_after)
                 VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (report_id, address) DO NOTHING
              RETURNING *
        """, (address, notif_type.lower(), json.dumps(data), report_id, ignore_after))
        if r is None:
            # Already done
            continue
        # Attempt to notify the user(s)
        participants = website.db.all("""
            SELECT p
              FROM emails e
              JOIN participants p ON p.id = e.participant
             WHERE lower(e.address) = lower(%s)
               AND (p.email IS NULL OR lower(p.email) = lower(e.address))
        """, (address,))
        for p in participants:
            try:
                p.notify('email_blacklisted', email=False, web=True, type='warning',
                         blacklisted_address=address, reason=r.reason)
            except DuplicateNotification:
                continue
    msg.delete()


def clean_up_emails():
    website.db.run("""
        DELETE FROM emails
         WHERE participant IS NULL
           AND added_time < (current_timestamp - interval '1 year');
        UPDATE emails
           SET nonce = NULL
         WHERE added_time < (current_timestamp - interval '1 year');
    """)
