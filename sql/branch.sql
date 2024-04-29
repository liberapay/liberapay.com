INSERT INTO app_conf VALUES ('openstreetmap_access_token_url', '"https://master.apis.dev.openstreetmap.org/oauth2/token"') ON CONFLICT (key) DO NOTHING;
UPDATE app_conf SET value = '"https://master.apis.dev.openstreetmap.org/api/0.6"' WHERE key = 'openstreetmap_api_url';
UPDATE app_conf SET value = '"https://master.apis.dev.openstreetmap.org/oauth2/authorize"' WHERE key = 'openstreetmap_auth_url';
UPDATE app_conf SET value = '"xAVaXxy0BwUef4SIo55v7E1ofuC53EN8H-X5232d8Vo"' WHERE key = 'openstreetmap_id';
UPDATE app_conf SET value = '"JtqazsotvWZQ1G6ynYhDlHXouQji-qDwwU2WQW7j-kE"' WHERE key = 'openstreetmap_secret';
