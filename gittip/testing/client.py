from __future__ import print_function, unicode_literals

from Cookie import SimpleCookie
from StringIO import StringIO

from aspen.http.request import Request
from aspen.testing import StubWSGIRequest
from gittip.security.user import User
from gittip.testing import test_website


BOUNDARY = b'BoUnDaRyStRiNg'
MULTIPART_CONTENT = b'multipart/form-data; boundary=%s' % BOUNDARY


def encode_multipart(boundary, data):
    """
    Encodes multipart POST data from a dictionary of form values.

    Borrowed from Django
    The key will be used as the form data name; the value will be transmitted
    as content. If the value is a file, the contents of the file will be sent
    as an application/octet-stream; otherwise, str(value) will be sent.
    """
    lines = []

    for (key, value) in data.items():
        lines.extend([
            b'--' + boundary,
            b'Content-Disposition: form-data; name="%s"' % str(key),
            b'',
            str(value)
        ])

    lines.extend([
        b'--' + boundary + b'--',
        b'',
    ])
    return b'\r\n'.join(lines)


# XXX TODO: Move the TestClient up into the Aspen code base so it can be shared
#           and used on other OSS projects.

class TestClient(object):

    def __init__(self):
        self.cookies = SimpleCookie()

    def get_request(self, path, method="GET", body=None,
                    **extra):
        env = StubWSGIRequest(path.encode('utf8'))
        env[b'REQUEST_METHOD'] = method.encode('utf8')
        env[b'wsgi.input'] = StringIO(body)
        env[b'HTTP_COOKIE'] = self.cookies.output(header='', sep='; ').encode('utf8')
        for k,v in extra.items():
            env[k.encode('utf8')] = v.encode('utf8')
        return Request.from_wsgi(env)

    def perform_request(self, request, user):
        request.website = test_website
        if user is not None:
            user = User.from_username(user)
            user.sign_in()
            # Note that Cookie needs a bytestring.
            request.headers.cookie[str('session')] = \
                                                 user.participant.session_token

        response = test_website.handle_safely(request)
        if response.headers.cookie:
            self.cookies.update(response.headers.cookie)
        return response

    def post(self, path, data, user=None, content_type=MULTIPART_CONTENT,
             **extra):
        """Perform a dummy POST request against the test website.

        :param path:
            The url to perform the virutal-POST to.

        :param data:
            A dictionary or list of tuples to be encoded before being POSTed.

        :param user:
            The user id performing the POST.

        Any additional parameters will be sent as headers. NOTE that in Aspen
        (request.py make_franken_headers) only headers beginning with ``HTTP``
        are included in the request - and those are changed to no longer
        include ``HTTP``. There are currently 2 exceptions to this:
        ``'CONTENT_TYPE'``, ``'CONTENT_LENGTH'`` which are explicitly checked
        for.
        """
        post_data = data

        if content_type is MULTIPART_CONTENT:
            post_data = encode_multipart(BOUNDARY, data)

        request = self.get_request(path, "POST", post_data,
                                   CONTENT_TYPE=str(content_type),
                                   **extra)
        return self.perform_request(request, user)

    def get(self, path, user=None, **extra):
        request = self.get_request(path, "GET")
        return self.perform_request(request, user)
