from datetime import timedelta
from enum import Enum, auto
from ipaddress import ip_address
import json
import logging
from random import random
import re
from smtplib import SMTP, SMTPException, SMTPNotSupportedError, SMTPResponseException
import time

from aspen.simplates.pagination import parse_specline, split_and_escape
from aspen_jinja2_renderer import SimplateLoader
import boto3
from dns.exception import DNSException
from dns.resolver import Cache, NXDOMAIN, Resolver
from pando import Response
from pando.utils import utcnow

from liberapay.constants import EMAIL_RE
from liberapay.exceptions import (
    BadEmailAddress, BrokenEmailDomain, DuplicateNotification, EmailDomainUnresolvable,
    EmailAddressError, EmailAddressIsBlacklisted, EmailDomainIsBlacklisted,
    InvalidEmailDomain, NonEmailDomain, EmailAddressRejected, TooManyAttempts,
)
from liberapay.renderers.jinja2 import Environment
from liberapay.utils import deserialize
from liberapay.website import website


class EmailVerificationResult(Enum):
    FAILED = auto()
    LOGIN_REQUIRED = auto()
    REDUNDANT = auto()
    STYMIED = auto()
    SUCCEEDED = auto()


jinja_env = Environment()
jinja_env_html = Environment(autoescape=True)

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
        if i == 1:
            assert not page.content
            continue
        tmpl = '\n' * page.offset + page.content
        content_type, renderer = parse_specline(page.header)
        env = jinja_env_html if content_type == 'text/html' else jinja_env
        r[content_type] = SimplateLoader(fpath, tmpl).load(env, fpath)
    return r


DNS = Resolver()
DNS.lifetime = 5.0  # limit queries to 5 seconds
DNS.cache = Cache()


class NormalizedEmailAddress(str):

    def __new__(cls, email):
        raise NotImplementedError("call the `normalize_email_address` function instead")

    @property
    def domain(self):
        return self[self.rfind('@')+1:]

    @property
    def local_part(self):
        return self[:self.rfind('@')]


def normalize_and_check_email_address(email: str) -> NormalizedEmailAddress:
    """Normalize and check an email address.

    Returns a `NormalizedEmailAddress` object.

    Raises:
        BadEmailAddress: if the address is syntactically unacceptable
        BrokenEmailDomain: if we're unable to establish an SMTP connection
        EmailAddressIsBlacklisted: if the address is in our blacklist
        EmailAddressRejected: if the SMTP server rejected the email address
        EmailDomainUnresolvable: if the DNS lookups fail
        EmailDomainIsBlacklisted: if the domain name is in our blacklist
        InvalidEmailDomain: if the domain name is syntactically invalid
        NonEmailDomain: if the domain doesn't accept email

    """
    email = normalize_email_address(email)
    check_email_address(email)
    return email


def normalize_email_address(email: str) -> NormalizedEmailAddress:
    """Normalize an email address.

    Returns a `NormalizedEmailAddress` object.

    Raises:
        BadEmailAddress: if the address is syntactically unacceptable
        InvalidEmailDomain: if the domain name is syntactically invalid

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
    except UnicodeError as e:
        raise InvalidEmailDomain(email, domain, e)

    # Check the syntax and length of the address
    email = local_part + '@' + domain
    if not EMAIL_RE.match(email) or len(email) > 320:
        # The length limit is from https://tools.ietf.org/html/rfc3696#section-3
        raise BadEmailAddress(email)

    return str.__new__(NormalizedEmailAddress, email)


port_25_is_open = None


def check_email_address(email: NormalizedEmailAddress) -> None:
    """Check that an email address isn't blacklisted and has a valid domain.

    Raises:
        BrokenEmailDomain: if we're unable to establish an SMTP connection
        EmailAddressIsBlacklisted: if the address is in our blacklist
        EmailAddressRejected: if the SMTP server rejected the email address
        EmailDomainUnresolvable: if the DNS lookups fail
        EmailDomainIsBlacklisted: if the domain name is in our blacklist
        NonEmailDomain: if the domain doesn't accept email

    """
    # Check that the address isn't in our blacklist
    check_email_blacklist(email)

    # Check that we can send emails to this address
    if website.app_conf.check_email_domains:
        request = website.state.get({}).get('request')
        if request:
            website.db.hit_rate_limit('email.test', request.source, TooManyAttempts)
        try:
            test_email_address(email)
        except EmailAddressError as e:
            if isinstance(e, BrokenEmailDomain):
                global port_25_is_open
                if port_25_is_open is None:
                    try:
                        test_email_address(normalize_email_address(
                            'support@liberapay.com'
                        ))
                    except BrokenEmailDomain:
                        port_25_is_open = False
                    except Exception as e:
                        website.tell_sentry(e)
                    else:
                        port_25_is_open = True
                if port_25_is_open is False:
                    website.tell_sentry(e, allow_reraise=False)
                    return
            if request:
                bypass_error = request.body.get('email.bypass_error') == 'yes'
            else:
                bypass_error = False
            if bypass_error and e.bypass_allowed:
                website.db.hit_rate_limit('email.bypass_error', request.source, TooManyAttempts)
            else:
                raise
        except Exception as e:
            website.tell_sentry(e)


def test_email_address(email: NormalizedEmailAddress, timeout: float = 30.0):
    """Attempt to determine if the given email address can be reached.

    Raises:
        BrokenEmailDomain: if we're unable to establish an SMTP connection
        EmailAddressRejected: if the SMTP server rejected the email address
        EmailDomainUnresolvable: if the DNS lookups fail
        NonEmailDomain: if the domain doesn't accept email (RFC 7505)

    """
    start_time = time.monotonic()
    try:
        ip_addresses = get_email_server_addresses(email)
        exceptions = []
        n_ip_addresses = 0
        n_attempts = 0
        success = False
        for ip_addr in ip_addresses:
            n_ip_addresses += 1
            try:
                if website.app_conf.check_email_servers:
                    test_email_server(str(ip_addr), email, timeout * 0.7)
                success = True
                break
            except EmailAddressRejected:
                raise
            except (SMTPException, OSError) as e:
                exceptions.append(e)
            except Exception as e:
                website.tell_sentry(e)
                exceptions.append(e)
            n_attempts += 1
            if n_attempts >= 3:
                break
            time_elapsed = time.monotonic() - start_time
            timeout = website.app_conf.socket_timeout - time_elapsed
            if timeout <= 3:
                break
        if not success:
            if n_ip_addresses == 0:
                raise EmailDomainUnresolvable(email, (
                    "didn't find any public IP address to deliver emails to"
                ))
            raise BrokenEmailDomain(email, exceptions[0])
    except EmailAddressError:
        raise
    except NXDOMAIN:
        raise EmailDomainUnresolvable(email, "no such domain (NXDOMAIN)")
    except DNSException as e:
        raise EmailDomainUnresolvable(email, str(e))


def get_email_server_addresses(email):
    """Resolve an email domain to IP addresses.

    Yields `IPv4Address` and `IPv6Address` objects.

    Raises:
        NonEmailDomain: if the domain doesn't accept email (RFC 7505)
        DNSException: if a DNS query fails

    Spec: https://tools.ietf.org/html/rfc5321#section-5.1

    """
    domain = email.domain
    rrset = DNS.resolve(domain, 'MX', raise_on_no_answer=False).rrset
    if rrset:
        if len(rrset) == 1 and str(rrset[0].exchange) == '.':
            # This domain doesn't accept email. https://tools.ietf.org/html/rfc7505
            raise NonEmailDomain(
                email, f"the domain {domain} has a 'null MX' record (RFC 7505)"
            )
        # Sort the returned MX records
        records = sorted(rrset, key=lambda rec: (rec.preference, random()))
        mx_domains = [str(rec.exchange).rstrip('.') for rec in records]
    else:
        mx_domains = [domain]
    # Yield the IP addresses, in order, without duplicates
    # We limit ourselves to looking up a maximum of 5 domains
    exceptions = []
    seen = set()
    for mx_domain in mx_domains[:5]:
        try:
            mx_ip_addresses = get_public_ip_addresses(mx_domain)
        except (DNSException, OSError) as e:
            exceptions.append(e)
            continue
        except Exception as e:
            website.tell_sentry(e)
            exceptions.append(e)
            continue
        for addr in mx_ip_addresses:
            if addr not in seen:
                yield addr
                seen.add(addr)
    if exceptions:
        raise exceptions[0]


def get_public_ip_addresses(domain):
    """Resolve a domain name to public IP addresses.

    Returns a list of `IPv4Address` and `IPv6Address` objects.

    Raises `DNSException` if both the `A` and `AAAA` queries fail.

    """
    records = []
    exception = None
    try:
        records.extend(DNS.resolve(domain, 'A', raise_on_no_answer=False).rrset or ())
    except DNSException as e:
        exception = e
    try:
        records.extend(DNS.resolve(domain, 'AAAA', raise_on_no_answer=False).rrset or ())
    except DNSException:
        if exception:
            raise exception from None
    # Return the list of valid global IP addresses found
    addresses = []
    for rec in records:
        try:
            addr = ip_address(rec.address)
        except ValueError:
            continue
        if addr.is_global:
            addresses.append(addr)
    return addresses


enhanced_code_re = re.compile(r"(?<![0-9])[245]\.[0-9]{1,3}\.[0-9]{1,3}(?![0-9])")


def test_email_server(ip_address: str, email=None, timeout=None) -> None:
    """Attempt to connect to and interact with an SMTP server.

    Args:
        ip_address (str): the IP address of the SMTP server
        email (NormalizedEmailAddress): an email address we want to send a message to
        timeout (float | None): number of seconds to wait for a response from the SMTP server

    Raises:
        EmailAddressRejected: if `email` is provided and the server rejects it
        OSError: if a network-related system error occurs, for example if the IP
                 address is a v6 address but the system lacks an IPv6 route, or
                 if the connection times out
        SMTPResponseException: if the server sends an invalid response
        SMTPServerDisconnected: if the server hangs up on us or fails to respond
                                both correctly and quickly enough

    """
    smtp = SMTP(None, timeout=timeout, local_hostname=website.env.hostname or None)
    if website.env.logging_level == 'debug':
        smtp.set_debuglevel(2)
    try:
        code = smtp.connect(ip_address)[0]
        if code < 0:
            raise SMTPResponseException(code, "first line received from server is invalid")
        if not email:
            return
        try:
            smtp.starttls()
            # A second EHLO or HELO is required after TLS has been established.
            smtp.ehlo_or_helo_if_needed()
        except SMTPNotSupportedError:
            pass
        status, msg = smtp.mail('')
        if status >= 400:
            enhanced_code, msg = parse_SMTP_reply(msg)
            error = repr(f"{status};{enhanced_code or ''} {msg}")
            if len(error) > 400:
                error = error[:399] + '…'
            website.logger.info(f"{ip_address} rejected MAIL command: {error}")
            return
        status, msg = smtp.rcpt(email)
        if status >= 400:
            # SMTP status codes: https://tools.ietf.org/html/rfc5321#section-4.2
            # Enhanced mail status codes:
            # https://www.iana.org/assignments/smtp-enhanced-status-codes/
            enhanced_code, msg = parse_SMTP_reply(msg)
            if enhanced_code:
                cls, subject, detail = enhanced_code.split('.')
            else:
                cls = subject = detail = None
            recipient_rejected = (
                cls and cls in '45' and (
                    # Address errors
                    subject == '1' and detail in '12346' or
                    # Mailbox errors
                    subject == '2' and detail in '124'
                ) or
                # gamil.com SMTP server
                msg.startswith("sorry, no mailbox here by that name") or
                # Microsoft's SMTP server
                msg.startswith("Requested action not taken: mailbox unavailable") or
                # OpenSMTPD
                msg.startswith("Invalid recipient: ") or
                # Tutanota's SMTP server
                msg.endswith("Recipient address rejected: Recipient not found")
            )
            if recipient_rejected:
                raise EmailAddressRejected(email, msg, ip_address)
    finally:
        try:
            smtp.close()
        except Exception:
            pass


def parse_SMTP_reply(msg: bytes):
    """Look for an enhanced mail status code, and collapse into a single line.
    """
    msg = msg.decode('utf8', errors='backslashreplace')
    enhanced_code = enhanced_code_re.match(msg)
    if enhanced_code:
        enhanced_code = enhanced_code[0]
        # Some SMTP servers (e.g. Google's) repeat the enhanced status code at
        # the beginning of each line of the response. We remove it to get a more
        # readable message.
        lines = msg.split('\n')
        if all(line.startswith(enhanced_code) or not line for line in lines):
            msg = ' '.join(line[len(enhanced_code):].lstrip() for line in lines)
        else:
            msg = msg[len(enhanced_code):].lstrip()
        del lines
    else:
        msg = msg.replace('\n', ' ')
    return enhanced_code, msg


def check_email_blacklist(address, check_domain=True):
    """
    Raises `EmailAddressIsBlacklisted` or `EmailDomainIsBlacklisted` if the
    given email address or its domain is blacklisted.
    """
    r = website.db.one("""
        SELECT reason, ts, details, ses_data
          FROM email_blacklist
         WHERE lower(address) = lower(%s)
           AND (ignore_after IS NULL OR ignore_after > current_timestamp)
      ORDER BY reason = 'complaint' DESC, ts DESC
         LIMIT 1
    """, (address,))
    if r:
        raise EmailAddressIsBlacklisted(address, r.reason, r.ts, r.details, r.ses_data)
    if not check_domain:
        return
    domain = address[address.rfind('@')+1:]
    r = website.db.one("""
        SELECT reason, ts, details
          FROM email_blacklist
         WHERE lower(address) = '@' || lower(%s)
           AND (ignore_after IS NULL OR ignore_after > current_timestamp)
      ORDER BY ts DESC
         LIMIT 1
    """, (domain,))
    if r:
        raise EmailDomainIsBlacklisted(domain, r.reason, r.ts, r.details)


def get_bounce_message(reason, ses_data, details):
    if reason != 'bounce':
        return
    if ses_data:
        bouncedRecipients = ses_data.get('bounce', {}).get('bouncedRecipients')
        if bouncedRecipients:
            recipient = bouncedRecipients[0]
            return recipient.get('diagnosticCode') or recipient.get('status')
    elif details:
        return details


class EmailError:
    """Represents an email bounce or complaint.
    """

    __slots__ = ('email_address', 'reason', 'ts', 'details', 'ses_data')

    def __init__(self, email_address, reason, ts, details, ses_data):
        self.email_address = email_address
        self.reason = reason
        self.ts = ts
        self.details = details
        self.ses_data = ses_data

    def get_bounce_message(self):
        return get_bounce_message(self.reason, self.ses_data, self.details)


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
                website.tell_sentry(e)
        time.sleep(1)


def _handle_ses_notification(msg):
    # Doc: https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html
    data = json.loads(json.loads(msg.body)['Message'])
    notif_type = data['notificationType']
    transient = False
    if notif_type == 'Bounce':
        bounce = data['bounce']
        report_id = bounce['feedbackId']
        recipients = bounce['bouncedRecipients']
        if bounce.get('bounceType') == 'Transient':
            transient = True
            bounce_subtype = bounce.get('bounceSubType')
            if bounce_subtype not in ('General', 'MailboxFull'):
                website.warning("unhandled bounce subtype: %r" % bounce_subtype)
    elif notif_type == 'Complaint':
        complaint = data['complaint']
        report_id = complaint['feedbackId']
        recipients = complaint['complainedRecipients']
        complaint_type = complaint.get('complaintFeedbackType')
        if complaint.get('complaintSubType') == 'OnAccountSuppressionList':
            pass
        elif complaint_type is None:
            # This complaint is invalid, ignore it.
            logging.info(
                "Received an invalid email complaint without a Feedback-Type. ID: %s" %
                report_id
            )
            msg.delete()
            return
        elif complaint_type not in ('abuse', 'fraud'):
            # We'll figure out how to deal with that when it happens.
            raise ValueError(complaint_type)
    else:
        raise ValueError(notif_type)
    for recipient in recipients:
        address = recipient['emailAddress']
        if address[-1] == '>':
            address = address[:-1].rsplit('<', 1)[1]
        if notif_type == 'Bounce':
            # Check the reported delivery status
            # Spec: https://tools.ietf.org/html/rfc3464#section-2.3.3
            action = recipient.get('action')
            if action is None:
                # This isn't a standard bounce. It may be a misdirected automatic reply.
                continue
            elif action == 'failed':
                # This is the kind of DSN we're interested in.
                pass
            elif action == 'delivered':
                # The reporting MTA claims that the message has been successfully delivered.
                continue
            elif action in ('delayed', 'relayed', 'expanded'):
                # Ignore non-final DSNs.
                continue
            else:
                # This is a new or non-standard type of DSN, ignore it.
                continue
        # Check for recurrent "transient" errors
        if transient:
            ignore_after = utcnow() + timedelta(days=5)
            n_previous_bounces = website.db.one("""
                SELECT count(*)
                  FROM email_blacklist
                 WHERE lower(address) = lower(%s)
                   AND ts > (current_timestamp - interval '90 days')
                   AND reason = 'bounce'
            """, (address,))
            if n_previous_bounces >= 2:
                ignore_after = utcnow() + timedelta(days=180)
        else:
            ignore_after = None
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
        bounce_message = get_bounce_message(r.reason, r.ses_data, r.details)
        participants = website.db.all("""
            SELECT p
              FROM emails e
              JOIN participants p ON p.id = e.participant
             WHERE lower(e.address) = lower(%s)
               AND (p.email IS NULL OR lower(p.email) = lower(e.address))
        """, (address,))
        for p in participants:
            try:
                p.notify(
                    'email_blacklisted', email=False, web=True, type='warning',
                    blacklisted_address=address, reason=r.reason,
                    ignore_after=r.ignore_after, bounce_message=bounce_message,
                )
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
         WHERE added_time < (current_timestamp - interval '1 year')
           AND nonce IS NOT NULL;
    """)


def remove_email_address_from_blacklist(address, user, request):
    """
    This function allows anyone to remove an email address from the blacklist,
    but with rate limits for non-admins in order to prevent abuse.
    """
    with website.db.get_cursor() as cursor:
        if not user.is_acting_as('admin'):
            source = user.id or request.source
            website.db.hit_rate_limit('email.unblacklist.source', source, TooManyAttempts)
        r = cursor.all("""
            UPDATE email_blacklist
               SET ignore_after = current_timestamp
                 , ignored_by = %(user_id)s
             WHERE lower(address) = lower(%(address)s)
               AND (ignore_after IS NULL OR ignore_after > current_timestamp)
         RETURNING *
        """, dict(address=address, user_id=user.id))
        if not r:
            return
        if not user.is_acting_as('admin'):
            if any(bl.reason == 'complaint' for bl in r):
                raise Response(403, (
                    "Only admins are allowed to unblock an address which is "
                    "blacklisted because of a complaint."
                ))
            website.db.hit_rate_limit('email.unblacklist.target', address, TooManyAttempts)
    # Mark the matching `email_blacklisted` notifications as read
    participant = website.db.Participant.from_email(address)
    if participant:
        notifications = website.db.all("""
            SELECT id, context
              FROM notifications
             WHERE participant = %s
               AND event = 'email_blacklisted'
               AND is_new
        """, (participant.id,))
        for notif in notifications:
            context = deserialize(notif.context)
            if context['blacklisted_address'].lower() == address.lower():
                participant.mark_notification_as_read(notif.id)
