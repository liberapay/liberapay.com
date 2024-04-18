import logging
import os
from os.path import join, dirname, realpath

from vcr import VCR
import yaml


TOP = realpath(join(dirname(dirname(__file__)), '..'))
FIXTURES_ROOT = join(TOP, 'tests', 'py', 'fixtures')


_logger = logging.getLogger('vcr.matchers')
_logger.setLevel(logging.INFO)


def filter_x_headers(headers):
    for k in list(headers.keys()):
        if k.startswith('x-'):
            headers.pop(k)


class CustomSerializer:

    @staticmethod
    def serialize(cassette_dict):
        for i in cassette_dict['interactions']:
            # Remove request headers
            i['request']['headers'] = {}
            # Filter some unimportant response headers
            response_headers = i['response']['headers']
            response_headers.pop('connection', None)
            response_headers.pop('date', None)
            response_headers.pop('server', None)
            filter_x_headers(response_headers)
        return yaml.dump(cassette_dict, default_flow_style=None, Dumper=yaml.Dumper)

    @staticmethod
    def deserialize(cassette_str):
        return yaml.safe_load(cassette_str)


vcr = VCR(
    cassette_library_dir=FIXTURES_ROOT,
    record_mode=os.environ.get('VCR', 'once'),
    match_on=['method', 'scheme', 'host', 'path', 'query'],
)
vcr.register_serializer('custom', CustomSerializer)


def use_cassette(name):
    return vcr.use_cassette(
        '{}.yml'.format(name),
        serializer='custom',
    )
