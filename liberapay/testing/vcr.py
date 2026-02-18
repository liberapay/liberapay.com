import logging
import os
from os.path import join, dirname, realpath
from unittest.mock import MagicMock

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


# https://vcrpy.readthedocs.io/en/latest/usage.html#record-modes
record_mode = os.environ.get('VCR', 'once')
if record_mode == 'off':
    vcr = MagicMock()
else:
    vcr = VCR(
        cassette_library_dir=FIXTURES_ROOT,
        decode_compressed_response=True,
        match_on=['method', 'scheme', 'host', 'path', 'query'],
        record_mode=record_mode,
        record_on_exception=False,
    )
    vcr.register_serializer('custom', CustomSerializer)
