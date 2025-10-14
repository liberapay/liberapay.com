from base64 import b64decode, b64encode
from binascii import hexlify, unhexlify
from datetime import date, datetime, timedelta
import errno
import fnmatch
from hashlib import sha256
import hmac
from operator import getitem
import os
import re
import socket
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from pando import Response, json
from pando.utils import to_rfc822, utcnow
from markupsafe import Markup

from liberapay.constants import SAFE_METHODS
from liberapay.elsewhere._paginators import _modify_query
from liberapay.exceptions import (
    AuthRequired, ClosedAccount, LoginRequired, TooManyAdminActions,
)
from liberapay.models.community import Community
from liberapay.i18n.base import LOCALE_EN, add_helpers_to_context
from liberapay.i18n.currencies import CURRENCIES, CURRENCY_REPLACEMENTS
from liberapay.website import website
from liberapay.utils import cbor


BEGINNING_OF_EPOCH = to_rfc822(datetime(1970, 1, 1)).encode('ascii')


def get_participant(
    state, restrict=True, allow_member=False, redirect_canon=True, redirect_stub=True,
):
    """Get a participant from the ID or username in the request path.

    Args:
        restrict (bool): the page is private, restrict access to it
        allow_member (bool): allow members of a team to access this page
        redirect_canon (bool): allow redirecting the request to the canonical URL
        redirect_stub (bool): allow redirecting the request to the pledge page

    Returns a `Participant` or raises a `Response`.

    """
    request = state['request']
    response = state['response']
    user = state['user']
    slug = request.path['username']
    _ = state['_']

    if restrict and user.ANON:
        raise LoginRequired

    if slug.startswith('~'):
        try:
            value = int(slug[1:])
        except ValueError:
            raise response.error(404)
        if value < 0 or value > 9223372036854775807:
            raise response.error(404)
        participant = user if user and user.id == value else None
    elif slug:
        value = slug.lower()
        participant = user if user and user.username.lower() == value else None
    else:
        raise response.error(404)

    if participant is None:
        if type(value) is int:
            participant = website.db.Participant.from_id(value, _raise=False)
        else:
            participant = website.db.Participant.from_username(value)
        if participant is None:
            if type(value) is str:
                look_up_redirections(request, response)
            raise response.error(404)
        elif participant.kind == 'community':
            c_name = website.db.one("""
                SELECT name
                  FROM communities
                 WHERE participant = %s
            """, (participant.id,))
            raise response.redirect('/for/%s' % c_name)

    if request.method in SAFE_METHODS:
        if redirect_canon and slug != participant.username:
            canon = '/' + participant.username + request.line.uri.decoded[len(slug)+1:]
            raise response.redirect(canon)
    else:
        if restrict:
            user.require_write_permission()

    is_blocked = participant.is_suspended
    if (restrict or is_blocked) and participant != user:
        if allow_member and participant.kind == 'group' and user.member_of(participant):
            pass
        elif user.is_acting_as('admin'):
            log_admin_request(user, participant, request)
        elif restrict:
            raise response.error(403, _("You are not authorized to access this page."))
        elif is_blocked:
            raise response.render('simplates/blocked-profile.spt', state)

    status = participant.status
    if status == 'closed':
        if not user.is_acting_as('admin'):
            raise ClosedAccount(participant)
    elif status == 'stub':
        if redirect_stub:
            to = participant.resolve_stub()
            if not to:
                # Account has been taken over
                raise response.error(404)
            raise response.redirect(to)

    if allow_member and (user == participant or participant.kind == 'group' and user.member_of(participant)):
        state['can_switch_account'] = True

    return participant


def get_community(state, restrict=False):
    request, response = state['request'], state['response']
    user = state['user']
    name = request.path['name']

    c = Community.from_name(name)
    if not c:
        raise response.error(404)
    if request.method in SAFE_METHODS:
        if c.name != name:
            response.redirect('/for/' + c.name + request.line.uri.decoded[5+len(name):])
    elif user.ANON:
        raise AuthRequired
    else:
        user.require_write_permission()

    is_blocked = c.participant.is_suspended
    if (restrict or is_blocked):
        if user.id == c.creator:
            pass
        elif user.is_acting_as('admin'):
            log_admin_request(user, c.participant, request)
        elif restrict:
            if user.ANON:
                raise LoginRequired
            else:
                _ = state['_']
                raise response.error(403, _("You are not authorized to access this page."))
        elif is_blocked:
            raise response.render('simplates/blocked-profile.spt', state)

    return c


def log_admin_request(admin, participant, request):
    if request.method not in SAFE_METHODS:
        website.db.hit_rate_limit('admin.http-unsafe', admin.id, TooManyAdminActions)
        action_data = {
            'method': request.method,
            'path': request.path.raw,
            'qs': dict(request.qs),
            'body': {
                k: (v[0] if len(v) == 1 else v)
                for k, v in request.body.items()
                if k != 'csrf_token'
            },
        }
        participant.add_event(website.db, 'admin_request', action_data, admin.id)


def look_up_redirections(request, response):
    path = request.path.raw
    if not path.endswith('/'):
        path += '/'
    r = website.db.one("""
        SELECT *
          FROM redirections
         WHERE starts_with(%s, from_prefix)
      ORDER BY length(from_prefix) DESC
         LIMIT 1
    """, (path.lower(),))
    if r:
        location = r.to_prefix + path[len(r.from_prefix.rstrip('%')):]
        response.redirect(location.rstrip('/'))


def form_post_success(state, msg='', redirect_url=None):
    """This function is meant to be called after a successful form POST.
    """
    request, response = state['request'], state['response']
    if request.headers.get(b'Accept', b'').startswith(b'application/json'):
        _ = state['_']
        raise response.json({"msg": msg or _("The changes have been saved.")})
    else:
        if not redirect_url:
            redirect_url = request.body.get('back_to') or request.line.uri.decoded
            redirect_url = response.sanitize_untrusted_url(redirect_url)
        redirect_url = _modify_query(redirect_url, 'success', b64encode_s(msg))
        response.redirect(redirect_url)


def b64decode_s(s, **kw):
    def error():
        if 'default' in kw:
            return kw['default']
        raise Response(400, "invalid base64 input")

    try:
        s = s.encode('ascii') if hasattr(s, 'encode') else s
    except UnicodeError:
        return error()

    udecode = lambda a: a.decode('utf8')
    if s[:1] == b'.':
        udecode = lambda a: a
        s = s[1:]
    s = s.replace(b'~', b'=')
    try:
        return udecode(b64decode(s, '-_'))
    except Exception:
        try:
            # For retrocompatibility
            return udecode(b64decode(s))
        except Exception:
            pass
        return error()


def b64encode_s(s):
    prefix = b''
    if not isinstance(s, bytes):
        s = s.encode('utf8')
    else:
        # Check whether the string is binary or already utf8
        try:
            s.decode('utf8')
        except UnicodeError:
            prefix = b'.'
    r = prefix + b64encode(s, b'-_').replace(b'=', b'~')
    return r.decode('ascii')


def excerpt_intro(text, length=175):
    if not text:
        return ''
    if isinstance(text, Markup):
        i = text.find('</p>')
        if i != -1:
            text = text[:i]
        text = text.striptags().strip()
    else:
        text = text.lstrip().split('\n', 1)[0].rstrip()
    if len(text) > length:
        text = text[:length]
        if text[-1] == '.':
            # don't add an ellipsis directly after a dot
            return text + ' […]'
        if text[-1] != ' ':
            # try to avoid cutting a word
            i = text.rfind(' ')
            if i > 0.9 * length:
                text = text[:i+1]
        return text + '…'
    return text


def is_card_expired(exp_year, exp_month):
    today = date.today()
    cur_year, cur_month = today.year, today.month
    return exp_year < cur_year or exp_year == cur_year and exp_month < cur_month


def get_owner_name(account):
    if not account:
        return ''
    if account.PersonType == 'NATURAL':
        return account.FirstName + ' ' + account.LastName
    else:
        return account.Name


def get_owner_address(bank_account, mp_account):
    if not mp_account:
        return ''
    if bank_account:
        addr = bank_account.OwnerAddress
    elif mp_account.PersonType == 'NATURAL':
        addr = mp_account.Address
    else:
        addr = mp_account.HeadquartersAddress
    if not addr.Country:
        return None
    return addr


def obfuscate(n, x, y):
    return n[:x] + 'x'*len(n[x:y]) + n[y:]


def ensure_str(s):
    if isinstance(s, str):
        return s
    return s.decode('ascii') if isinstance(s, bytes) else s.encode('ascii')


def set_cookie(cookies, key, value, expires=None, httponly=True, path='/', samesite='lax'):
    key = ensure_str(key)
    cookies[key] = ensure_str(value)
    cookie = cookies[key]
    if expires:
        if isinstance(expires, timedelta):
            expires += utcnow()
        if isinstance(expires, datetime):
            expires = to_rfc822(expires)
        cookie['expires'] = ensure_str(expires)
    if httponly:
        cookie['httponly'] = True
    if path:
        cookie['path'] = ensure_str(path)
    if samesite:
        cookie['samesite'] = ensure_str(samesite)
    if website.cookie_domain:
        cookie['domain'] = ensure_str(website.cookie_domain)
    if website.canonical_scheme == 'https':
        cookie['secure'] = True


def erase_cookie(cookies, key, **kw):
    set_cookie(cookies, key, '', BEGINNING_OF_EPOCH, **kw)


def to_javascript(obj):
    """For when you want to inject an object into a <script> tag.
    """
    return json.dumps(obj).replace('</', '<\\/')


svg_attrs_re = re.compile(r'\s+(?:height|width|x|y|xmlns)=(["\']).*?\1')

def include_svg(svg, height, width, x=None, y=None):
    """For when you want to include an SVG in an HTML page or in another SVG.
    """
    assert svg.startswith('<svg')
    i = svg.find('>')
    assert i != -1
    d = locals()
    attrs = svg_attrs_re.sub('', svg[4:i])
    for a in ('height', 'width', 'x', 'y'):
        v = d[a]
        if v is None:
            continue
        attrs += ' %s="%s"' % (a, v)
    return Markup(svg[:4] + attrs + svg[i:])


def group_by(iterable, key, attr=False, ignored_exceptions=KeyError):
    r = {}
    if callable(key):
        for obj in iterable:
            k = key(obj)
            r.setdefault(k, []).append(obj)
        return r
    f = getattr if attr else getitem
    for obj in iterable:
        try:
            k = f(obj, key)
        except ignored_exceptions:
            continue
        r.setdefault(k, []).append(obj)
    return r


def find_files(directory, pattern):
    for root, dirs, files in os.walk(directory):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(root, filename)


def serialize(context):
    for k, v in context.items():
        if callable(getattr(v, '_asdict', None)):
            context[k] = v._asdict()
    return b'\\x' + hexlify(cbor.dumps(context, canonical=True))


def deserialize(context):
    if isinstance(context, memoryview) and context[:2].tobytes() == b'\\x':
        context = unhexlify(context[2:])
    return cbor.loads(context)


def pid_exists(pid):
    """Check whether pid exists in the current process table. UNIX only.

    Source: http://stackoverflow.com/a/6940314/2729778
    """
    if not pid > 0:
        raise ValueError("bad PID %s" % pid)
    try:
        os.kill(pid, 0)
    except OSError as err:
        if err.errno == errno.ESRCH:
            # ESRCH == No such process
            return False
        elif err.errno == errno.EPERM:
            # EPERM clearly means there's a process to deny access to
            return True
        else:
            # According to "man 2 kill" possible error values are
            # (EINVAL, EPERM, ESRCH)
            raise
    else:
        return True


def build_s3_object_url(key):
    now = utcnow()
    timestamp = now.strftime('%Y%m%dT%H%M%SZ')
    today = timestamp.split('T', 1)[0]
    region = website.app_conf.s3_region
    access_key = website.app_conf.s3_public_access_key
    endpoint = website.app_conf.s3_endpoint
    assert endpoint.startswith('https://')
    host = endpoint[8:]
    querystring = (
        f"X-Amz-Algorithm=AWS4-HMAC-SHA256&"
        f"X-Amz-Credential={access_key}%2F{today}%2F{region}%2Fs3%2Faws4_request&"
        f"X-Amz-Date={timestamp}&"
        f"X-Amz-Expires=86400&"
        f"X-Amz-SignedHeaders=host"
    )
    canonical_request = (
        f"GET\n"
        f"/{key}\n"
        f"{querystring}\n"
        f"host:{host}\n"
        f"\n"
        f"host\n"
        f"UNSIGNED-PAYLOAD"
    ).encode()
    canonical_request_hash = sha256(canonical_request).hexdigest()
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n"
        f"{timestamp}\n"
        f"{today}/{region}/s3/aws4_request\n"
        f"{canonical_request_hash}"
    ).encode()
    aws4_secret_key = b"AWS4" + website.app_conf.s3_secret_key.encode()
    sig_key = hmac.new(aws4_secret_key, today.encode(), sha256).digest()
    sig_key = hmac.new(sig_key, region.encode(), sha256).digest()
    sig_key = hmac.new(sig_key, b"s3", sha256).digest()
    sig_key = hmac.new(sig_key, b"aws4_request", sha256).digest()
    signature = hmac.new(sig_key, string_to_sign, sha256).hexdigest()
    return endpoint + "/" + key + "?" + querystring + "&X-Amz-Signature=" + signature


NO_DEFAULT = object()


def get_int(d, k, default=NO_DEFAULT, minimum=0, maximum=2**63-1):
    try:
        r = d[k]
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    try:
        r = int(r)
    except (ValueError, TypeError):
        raise Response().error(400, "`%s` value %r is not a valid integer" % (k, r))
    if minimum is not None and r < minimum:
        raise Response().error(400, "`%s` value %r is less than %i" % (k, r, minimum))
    if maximum is not None and r > maximum:
        raise Response().error(400, "`%s` value %r is greater than %i" % (k, r, maximum))
    return r


def get_currency(d, k, default=NO_DEFAULT, phased_out='allow'):
    try:
        currency = d[k]
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    if currency not in CURRENCIES:
        replacement = CURRENCY_REPLACEMENTS.get(currency)
        if replacement and phased_out in ('allow', 'replace'):
            if phased_out == 'replace':
                currency = replacement[1]
        else:
            raise Response().error(
                400, "`%s` value %r isn't a supported currency code" % (k, currency)
            )
    return currency


def get_money_amount(d, k, currency, default=NO_DEFAULT):
    try:
        r = d[k]
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    return LOCALE_EN.parse_money_amount(r, currency)


def get_choice(d, k, choices, default=NO_DEFAULT):
    try:
        r = d[k]
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    if r not in choices:
        raise Response().error(400, "`%s` value %r is invalid. Choices: %r" % (k, r, choices))
    return r


color_re = re.compile(r"^[0-9a-f]{6}$")


def get_color(d, k, default=NO_DEFAULT):
    try:
        r = d[k]
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    if not color_re.match(r):
        raise Response().error(400, "`%s` value %r is not a valid hexadecimal color" % (k, r))
    return r


def word(mapping, k, pattern=r'^\w+$', unicode=False):
    r = mapping[k]
    if not r:
        raise Response().error(400, "`%s` value %r is empty" % (k, r))
    if not re.match(pattern, r, re.UNICODE if unicode else re.ASCII):
        raise Response().error(400, "`%s` value %r contains forbidden characters" % (k, r))
    return r


FALSEISH = {'0', 'f', 'false', 'n', 'no', 'off'}
TRUEISH = {'1', 't', 'true', 'y', 'yes', 'on'}
NULLISH = {'', 'null', 'none'}


def parse_boolean(mapping, k, default=NO_DEFAULT):
    try:
        r = mapping[k].lower()
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    if r in TRUEISH:
        return True
    if r in FALSEISH:
        return False
    raise Response().error(400, "`%s` value %r is invalid" % (k, r))


def parse_ternary(mapping, k, default=NO_DEFAULT):
    try:
        r = mapping[k].lower()
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    if r in TRUEISH:
        return True
    if r in FALSEISH:
        return False
    if r in NULLISH:
        return None
    raise Response().error(400, "`%s` value %r is invalid" % (k, r))


def parse_date(mapping, k, default=NO_DEFAULT, sep='-'):
    try:
        r = mapping[k]
        if r:
            r = r.split(sep)
        elif default is not NO_DEFAULT:
            return default
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    try:
        year, month, day = map(int, r)
        # the above raises ValueError if the number of parts isn't 3
        # or if any part isn't an integer
        r = date(year, month, day)
    except (ValueError, TypeError):
        raise Response().error(400, "`%s` value %r is invalid" % (k, mapping[k]))
    return r


def parse_list(mapping, k, cast, default=NO_DEFAULT, sep=','):
    try:
        r = mapping[k].split(sep)
    except (KeyError, Response):
        if default is NO_DEFAULT:
            raise
        return default
    try:
        r = [cast(v) for v in r]
    except (ValueError, TypeError):
        raise Response().error(400, "`%s` value %r is invalid" % (k, mapping[k]))
    return r


def parse_int(o, default=NO_DEFAULT, minimum=0, maximum=2**63-1):
    try:
        r = int(o)
    except (ValueError, TypeError):
        if default is NO_DEFAULT:
            raise Response().error(400, "%r is not a valid integer" % o)
        return default
    if minimum is not None and r < minimum:
        raise Response().error(400, f"{r} is less than {minimum}")
    if maximum is not None and r > maximum:
        raise Response().error(400, f"{r} is greater than {maximum}")
    return r


def check_address(addr):
    for k in ('AddressLine1', 'City', 'PostalCode', 'Country'):
        if not addr.get(k):
            return False
    if addr['Country'] == 'US' and not addr.get('Region'):
        return False
    return True


def check_address_v2(addr):
    if not addr:
        return False
    for k in ('country', 'city', 'postal_code', 'local_address'):
        if not addr.get(k):
            return False
    if addr['country'] == 'US' and not addr.get('region'):
        # FIXME This is simplistic, `region` can be required in other countries too.
        # Related: https://github.com/liberapay/liberapay.com/issues/1056
        return False
    return True


def render_postal_address(addr, single_line=False, format='local'):
    if not check_address_v2(addr):
        return
    if format == 'local':
        # FIXME The rendering below is simplistic, we should implement
        #       https://github.com/liberapay/liberapay.com/issues/1056
        elements = [addr['local_address'], addr['city'], addr['postal_code']]
        if addr.get('region'):
            elements.append(addr['region'])
        elements.append(LOCALE_EN.countries[addr['country']])
        sep = ', ' if single_line else '\n'
    elif format == 'downward':
        elements = [LOCALE_EN.countries[addr['country']]]
        if addr.get('region'):
            elements.append(addr['region'])
        elements += [addr['city'], addr['postal_code'], addr['local_address']]
        sep = ' / ' if single_line else '\n'
    else:
        raise ValueError(f"unknown `format` value {format!r}")
    return sep.join(elements)


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            return
        raise


def get_ip_net(addr):
    if addr.max_prefixlen == 32:
        return '.'.join(str(addr).split('.', 2)[:2])
    else:
        return ':'.join(str(addr).split(':', 2)[:2])


def render(context, allow_partial_i18n=True):
    """Render the next page and return the output.

    This function is meant to be used in the second page of a simplate, e.g.:

    ```
    from liberapay.utils import render
    [---]
    output.body = render(globals(), allow_partial_i18n=False)
    [---] text/html
    ...
    ```

    If `allow_partial_i18n` is `False` and the output is a partially translated
    page then a second rendering is done so that the final output is entirely in
    English.
    """
    output, resource = context['output'], context['resource']
    r = resource.renderers[output.media_type](context)
    if allow_partial_i18n or not context['state'].get('partial_translation'):
        return r
    else:
        # Fall back to English
        add_helpers_to_context(context, LOCALE_EN)
        return resource.renderers[output.media_type](context)


def resolve(domain, port):
    try:
        return socket.getaddrinfo(domain, port)
    except socket.gaierror:
        return


def partition(l, predicate):
    a, b = [], []
    for e in l:
        if predicate(e):
            a.append(e)
        else:
            b.append(e)
    return a, b


def get_recordable_headers(request):
    decode = lambda b: b.decode('ascii', 'backslashreplace')
    r = {
        decode(k): decode(b', '.join(v))
        for k, v in request.headers.items()
        if k != b'Cookie'
    }
    r['Cookie'] = {
        name: len(value) for name, value in request.cookies.items()
    }
    return r


def tweak_avatar_url(avatar_url, increment=True):
    if not avatar_url:
        return ''
    # Parse the URL
    scheme, netloc, path, query, fragment = urlsplit(avatar_url)
    query = parse_qs(query)
    # Add parameters inherited from Gravatar (https://wiki.libravatar.org/api/)
    query['s'] = '160'  # size = 160 pixels
    query['d'] = '404'  # default = a 404 HTTP response
    # Increment the serial number to avoid stale images in a browser's cache
    try:
        query[''] = str(int(query[''][-1]) + int(increment))
    except (KeyError, ValueError):
        query[''] = '1'
    # Drop any fragment that might be there
    fragment = ''
    # Return the modified URL
    return urlunsplit((scheme, netloc, path, urlencode(query), fragment))
