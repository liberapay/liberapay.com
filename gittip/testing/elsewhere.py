# -*- coding: utf-8 -*-

"""
Examples of data returned by the APIs of the elsewhere platforms.

They are wrapped in lambdas to prevent tests from persistently modifying the
data.
"""

import xml.etree.ElementTree as ET

bitbucket = lambda: {
    "repositories": [
        {
            "scm": "hg",
            "has_wiki": True,
            "last_updated": "2012-03-16T23:36:38.019",
            "no_forks": None,
            "created_on": "2012-03-16T23:34:46.740",
            "owner": "whit537",
            "logo": "https://d3oaxc4q5k2d6q.cloudfront.net/m/6fac1fb24100/img/language-avatars/default_16.png",
            "email_mailinglist": "",
            "is_mq": False,
            "size": 142818,
            "read_only": False,
            "fork_of": {
                "scm": "hg",
                "has_wiki": True,
                "last_updated": "2014-02-01T03:41:46.920",
                "no_forks": None,
                "created_on": "2010-07-17T16:12:34.381",
                "owner": "jaraco",
                "logo": "https://d3oaxc4q5k2d6q.cloudfront.net/m/6fac1fb24100/img/language-avatars/python_16.png",
                "email_mailinglist": "",
                "is_mq": False,
                "size": 316601,
                "read_only": False,
                "creator": None,
                "state": "available",
                "utc_created_on": "2010-07-17 14:12:34+00:00",
                "website": "",
                "description": "Inspried by jezdez.setuptools_hg, and building on that work, hgtools provides tools for developing with mercurial and setuptools/distribute (specifically a file-finder plugin and automatic repo tag versioning).\r\n\r\nThe underlying library is designed to be extensible for other applications to build other functionality that depends on mercurial, whether using the 'hg' command or the mercurial libraries directly.",
                "has_issues": True,
                "is_fork": True,
                "slug": "hgtools",
                "is_private": False,
                "name": "hgtools",
                "language": "python",
                "utc_last_updated": "2014-02-01 02:41:46+00:00",
                "email_writers": True,
                "no_public_forks": False,
                "resource_uri": "/1.0/repositories/jaraco/hgtools"
            },
            "mq_of": {
                "scm": "hg",
                "has_wiki": True,
                "last_updated": "2014-02-01T03:41:46.920",
                "no_forks": None,
                "created_on": "2010-07-17T16:12:34.381",
                "owner": "jaraco",
                "logo": "https://d3oaxc4q5k2d6q.cloudfront.net/m/6fac1fb24100/img/language-avatars/python_16.png",
                "email_mailinglist": "",
                "is_mq": False,
                "size": 316601,
                "read_only": False,
                "creator": None,
                "state": "available",
                "utc_created_on": "2010-07-17 14:12:34+00:00",
                "website": "",
                "description": "Inspried by jezdez.setuptools_hg, and building on that work, hgtools provides tools for developing with mercurial and setuptools/distribute (specifically a file-finder plugin and automatic repo tag versioning).\r\n\r\nThe underlying library is designed to be extensible for other applications to build other functionality that depends on mercurial, whether using the 'hg' command or the mercurial libraries directly.",
                "has_issues": True,
                "is_fork": True,
                "slug": "hgtools",
                "is_private": False,
                "name": "hgtools",
                "language": "python",
                "utc_last_updated": "2014-02-01 02:41:46+00:00",
                "email_writers": True,
                "no_public_forks": False,
                "resource_uri": "/1.0/repositories/jaraco/hgtools"
            },
            "state": "available",
            "utc_created_on": "2012-03-16 22:34:46+00:00",
            "website": None,
            "description": "I'm forking to fix another bug case in issue #7.",
            "has_issues": True,
            "is_fork": True,
            "slug": "hgtools",
            "is_private": False,
            "name": "hgtools",
            "language": "",
            "utc_last_updated": "2012-03-16 22:36:38+00:00",
            "email_writers": True,
            "no_public_forks": False,
            "creator": None,
            "resource_uri": "/1.0/repositories/whit537/hgtools"
        }
    ],
    "user": {
        "username": "whit537",
        "first_name": "Chad",
        "last_name": "Whitacre",
        "display_name": "Chad Whitacre",
        "is_team": False,
        "avatar": "https://secure.gravatar.com/avatar/5698bc43665106a28833ef61c8a9f67f?d=https%3A%2F%2Fd3oaxc4q5k2d6q.cloudfront.net%2Fm%2F6fac1fb24100%2Fimg%2Fdefault_avatar%2F32%2Fuser_blue.png&s=32",
        "resource_uri": "/1.0/users/whit537"
    }
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
    "gittip_account": {
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
    "company": "Gittip",
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

venmo = lambda: {
    "about": "No Short Bio",
    "date_joined": "2013-09-11T19:57:53",
    "display_name": "Thomas Boyt",
    "email": None,
    "first_name": "Thomas",
    "friends_count": 30,
    "id": "1242868517699584789",
    "is_friend": False,
    "last_name": "Boyt",
    "phone": None,
    "profile_picture_url": "https://s3.amazonaws.com/venmo/no-image.gif",
    "username": "thomas-boyt"
}
