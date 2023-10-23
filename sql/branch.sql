UPDATE app_conf SET value = '"https://api.openstreetmap.org/api/0.6"'::jsonb WHERE key = 'openstreetmap_api_url';
UPDATE app_conf SET value = '"https://www.openstreetmap.org"'::jsonb WHERE key = 'openstreetmap_auth_url';
