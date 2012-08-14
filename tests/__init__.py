import os

from aspen.testing import Website, StubRequest


def set_up_test_environment():
    os.environ['CANONICAL_HOST'] = ''
    os.environ['CANONICAL_SCHEME'] = 'http'
    os.environ['DATABASE_URL'] = 'postgres://postgres@127.0.0.1/gittip-test'
    os.environ['BALANCED_API_SECRET'] = '90bb3648ca0a11e1a977026ba7e239a9'
    os.environ['STRIPE_SECRET_API_KEY'] = 'madeupkey'
    os.environ['STRIPE_PUBLISHABLE_API_KEY'] = 'madeupkey'
    os.environ['GITHUB_CLIENT_ID'] = '3785a9ac30df99feeef5'
    os.environ['GITHUB_CLIENT_SECRET'] = 'e69825fafa163a0b0b6d2424c107a49333d46985'
    os.environ['GITHUB_CALLBACK'] = 'http://localhost:8537/github/associate'
    os.environ['DYLD_LIBRARY_PATH'] = '/Library/PostgreSQL/9.1/lib'


def serve_request(path):
    """Given an URL path, return response"""
    request = StubRequest(path)
    request.website = test_website
    response = test_website.handle_safely(request)
    return response


set_up_test_environment()
test_website = Website(['--www_root', 'www/', '--project_root', '..'])
