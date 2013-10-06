from __future__ import print_function, unicode_literals

from aspen.http.request import UnicodeWithParams
from gittip.elsewhere import openstreetmap
from gittip.testing import Harness
import os


class TestElsewhereOpenStreetMap(Harness):

    def test_get_user_info_gets_user_info(self):
        user_info = {
            'osm_id': '1'
            , 'username': 'alice'
            , 'img_src': 'http://example.com'
            , 'html_url': 'http://example.net'
        }
        openstreetmap.OpenStreetMapAccount("1", user_info).opt_in('alice')
        expected = user_info
        actual = openstreetmap.get_user_info('alice', os.environ.get('OPENSRTEETMAP_API'))
        assert actual == expected

    def test_get_user_info_gets_user_info_from_UnicodeWithParams(self):
        user_info = {
            'osm_id': '1'
            , 'username': 'alice'
            , 'img_src': 'http://example.com'
            , 'html_url': 'http://example.net'
        }
        openstreetmap.OpenStreetMapAccount("1", user_info).opt_in('alice')
        expected = user_info
        actual = openstreetmap.get_user_info(UnicodeWithParams('alice', {}), os.environ.get('OPENSRTEETMAP_API'))
        assert actual == expected
