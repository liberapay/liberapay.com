from __future__ import unicode_literals

from aspen.simplates.pagination import parse_specline, split_and_escape
from aspen_jinja2_renderer import SimplateLoader
from dns.exception import DNSException
import dns.resolver as DNS
from jinja2 import Environment

from liberapay.constants import EMAIL_RE, JINJA_ENV_COMMON
from liberapay.exceptions import BadEmailAddress, BadEmailDomain
from liberapay.website import website


(
    VERIFICATION_MISSING,
    VERIFICATION_FAILED,
    VERIFICATION_EXPIRED,
    VERIFICATION_REDUNDANT,
    VERIFICATION_STYMIED,
    VERIFICATION_SUCCEEDED,
) = range(6)


jinja_env = Environment(**JINJA_ENV_COMMON)
jinja_env_html = Environment(
    autoescape=True, extensions=['jinja2.ext.autoescape'],
    **JINJA_ENV_COMMON
)

def compile_email_spt(fpath):
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
