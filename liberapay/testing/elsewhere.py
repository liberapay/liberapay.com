# -*- coding: utf-8 -*-

"""
Examples of data returned by the APIs of the elsewhere platforms.

They are wrapped in lambdas to prevent tests from persistently modifying the
data.
"""

import xml.etree.ElementTree as ET

bitbucket = lambda: {
    "username": "whit537",
    "website": "https://www.gittip.com/whit537/",
    "display_name": "Chad Whitacre",
    "uuid": "{59efeb39-29dc-415e-959e-3cb1ea7f579b}",
    "links": {
        "self": {
            "href": "https://bitbucket.org/api/2.0/users/whit537"
        },
        "repositories": {
            "href": "https://bitbucket.org/api/2.0/repositories/whit537"
        },
        "html": {
            "href": "https://bitbucket.org/whit537"
        },
        "followers": {
            "href": "https://bitbucket.org/api/2.0/users/whit537/followers"
        },
        "avatar": {
            "href": "https://secure.gravatar.com/avatar/5698bc43665106a28833ef61c8a9f67f?d=https%3A%2F%2Fd3oaxc4q5k2d6q.cloudfront.net%2Fm%2F5fe8c0346b2d%2Fimg%2Fdefault_avatar%2F32%2Fuser_blue.png&s=32"
        },
        "following": {
            "href": "https://bitbucket.org/api/2.0/users/whit537/following"
        }
    },
    "created_on": "2012-01-23T20:11:10.736097+00:00",
    "location": "Pittsburgh, PA USA",
    "type": "user"
}

bountysource = lambda: {
    "bio": "Code alchemist at Bountysource.",
    "twitter_account": {
        "uid": 313084547,
        "followers": None,
        "following": None,
        "image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/twitter_name/d_noaoqqwxegvmulwus0un.png,c_pad,w_100,h_100/corytheboyd.png",
        "login": "corytheboyd",
        "id": 2105
    },
    "display_name": "corytheboyd",
    "url": "",
    "type": "Person",
    "created_at": "2012-09-14T03:28:07Z",
    "slug": "6-corytheboyd",
    "facebook_account": {
        "uid": 589244295,
        "followers": 0,
        "following": 0,
        "image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/facebook/d_noaoqqwxegvmulwus0un.png,c_pad,w_100,h_100/corytheboyd.jpg",
        "login": "corytheboyd",
        "id": 2103
    },
    "gratipay_account": {
        "uid": 17306,
        "followers": 0,
        "following": 0,
        "image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/gravatar/d_noaoqqwxegvmulwus0un.png,c_pad,w_100,h_100/bdeaea505d059ccf23d8de5714ae7f73",
        "login": "corytheboyd",
        "id": 2067
    },
    "large_image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/twitter_name/d_noaoqqwxegvmulwus0un.png,c_pad,w_400,h_400/corytheboyd.png",
    "frontend_path": "/users/6-corytheboyd",
    "image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/twitter_name/d_noaoqqwxegvmulwus0un.png,c_pad,w_100,h_100/corytheboyd.png",
    "location": "San Francisco, CA",
    "medium_image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/twitter_name/d_noaoqqwxegvmulwus0un.png,c_pad,w_200,h_200/corytheboyd.png",
    "frontend_url": "https://www.bountysource.com/users/6-corytheboyd",
    "github_account": {
        "uid": 692632,
        "followers": 11,
        "following": 4,
        "image_url": "https://cloudinary-a.akamaihd.net/bountysource/image/gravatar/d_noaoqqwxegvmulwus0un.png,c_pad,w_100,h_100/bdeaea505d059ccf23d8de5714ae7f73",
        "login": "corytheboyd",
        "id": 89,
        "permissions": [
            "public_repo"
        ]
    },
    "company": "Bountysource",
    "id": 6,
    "public_email": "cory@bountysource.com"
}

github = lambda: {
    "bio": "",
    "updated_at": "2013-01-14T13:43:23Z",
    "gravatar_id": "fb054b407a6461e417ee6b6ae084da37",
    "hireable": False,
    "id": 134455,
    "followers_url": "https://api.github.com/users/whit537/followers",
    "following_url": "https://api.github.com/users/whit537/following",
    "blog": "http://whit537.org/",
    "followers": 90,
    "location": "Pittsburgh, PA",
    "type": "User",
    "email": "chad@zetaweb.com",
    "public_repos": 25,
    "events_url": "https://api.github.com/users/whit537/events{/privacy}",
    "company": "Gratipay",
    "gists_url": "https://api.github.com/users/whit537/gists{/gist_id}",
    "html_url": "https://github.com/whit537",
    "subscriptions_url": "https://api.github.com/users/whit537/subscriptions",
    "received_events_url": "https://api.github.com/users/whit537/received_events",
    "starred_url": "https://api.github.com/users/whit537/starred{/owner}{/repo}",
    "public_gists": 29,
    "name": "Chad Whitacre",
    "organizations_url": "https://api.github.com/users/whit537/orgs",
    "url": "https://api.github.com/users/whit537",
    "created_at": "2009-10-03T02:47:57Z",
    "avatar_url": "https://secure.gravatar.com/avatar/fb054b407a6461e417ee6b6ae084da37?d=https://a248.e.akamai.net/assets.github.com%2Fimages%2Fgravatars%2Fgravatar-user-420.png",
    "repos_url": "https://api.github.com/users/whit537/repos",
    "following": 15,
    "login": "whit537"
}

openstreetmap = lambda: ET.fromstring("""
 <!-- copied from http://wiki.openstreetmap.org/wiki/API_v0.6 -->
 <osm version="0.6" generator="OpenStreetMap server">
   <user id="12023" display_name="jbpbis" account_created="2007-08-16T01:35:56Z">
     <description></description>
     <contributor-terms agreed="false"/>
     <img href="http://www.gravatar.com/avatar/c8c86cd15f60ecca66ce2b10cb6b9a00.jpg?s=256&amp;d=http%3A%2F%2Fwww.openstreetmap.org%2Fassets%2Fusers%2Fimages%2Flarge-39c3a9dc4e778311af6b70ddcf447b58.png"/>
     <roles>
     </roles>
     <changesets count="1"/>
     <traces count="0"/>
     <blocks>
       <received count="0" active="0"/>
     </blocks>
   </user>
 </osm>
""")

twitter = lambda: {
    "lang": "en",
    "utc_offset": 3600,
    "statuses_count": 1339,
    "follow_request_sent": None,
    "friends_count": 81,
    "profile_use_background_image": True,
    "contributors_enabled": False,
    "profile_link_color": "0084B4",
    "profile_image_url": "http://pbs.twimg.com/profile_images/3502698593/36a503f65df33aea1a59faea77a57e73_normal.png",
    "time_zone": "Paris",
    "notifications": None,
    "is_translator": False,
    "favourites_count": 81,
    "profile_background_image_url_https": "https://abs.twimg.com/images/themes/theme1/bg.png",
    "profile_background_color": "C0DEED",
    "id": 23608307,
    "profile_background_image_url": "http://abs.twimg.com/images/themes/theme1/bg.png",
    "description": "#Freelance computer programmer from France. In English: #FreeSoftware and #BasicIncome. In French: #LogicielLibre, #RevenuDeBase and #Démocratie/#TirageAuSort.",
    "is_translation_enabled": False,
    "default_profile": True,
    "profile_background_tile": False,
    "verified": False,
    "screen_name": "Changaco",
    "entities": {
        "url": {
            "urls": [
                {
                    "url": "http://t.co/2VUhacI9SG",
                    "indices": [
                        0,
                        22
                    ],
                    "expanded_url": "http://changaco.oy.lc/",
                    "display_url": "changaco.oy.lc"
                }
            ]
        },
        "description": {
            "urls": []
        }
    },
    "url": "http://t.co/2VUhacI9SG",
    "profile_image_url_https": "https://pbs.twimg.com/profile_images/3502698593/36a503f65df33aea1a59faea77a57e73_normal.png",
    "profile_sidebar_fill_color": "DDEEF6",
    "location": "France",
    "name": "Changaco",
    "geo_enabled": False,
    "profile_text_color": "333333",
    "followers_count": 94,
    "profile_sidebar_border_color": "C0DEED",
    "id_str": "23608307",
    "default_profile_image": False,
    "following": None,
    "protected": False,
    "created_at": "Tue Mar 10 15:58:07 +0000 2009",
    "listed_count": 7
}

facebook = lambda: {
   "id": "187701977",
   "first_name": "Chad",
   "gender": "male",
   "last_name": "Whitacre",
   "link": "https://www.facebook.com/whit537",
   "locale": "en_US",
   "name": "Chad Whitacre",
   "username": "whit537"
}

google = lambda: {
    "kind": "plus#person",
    "displayName": "Paul Kuruvilla",
    "name": {
        "givenName": "Paul",
        "familyName": "Kuruvilla"
    },
    "language": "en",
    "isPlusUser": True,
    "url": "https://plus.google.com/+PaulKuruvilla",
    "gender": "male",
    "image": {
        "url": "https://lh6.googleusercontent.com/-IVBSagxBYtI/AAAAAAAAAAI/AAAAAAAAAPM/M6QeFhQ3DWs/photo.jpg?sz=50",
        "isDefault": False
    },
    "birthday": "1993-07-25",
    "id": "103133617858201182649",
    "etag": "\"L2Xbn8bDuSErT6QA3PEQiwYKQxM/0daBZaquM1pvzmFAQ_Z-Mp5CUok\"",
    "verified": False,
    "circledByCount": 255,
    "emails": [{
        "type": "account",
        "value": "rohitpaulk@live.com"
    }],
    "objectType": "person"
}
