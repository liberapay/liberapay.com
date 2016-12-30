-- For production
-- INSERT INTO app_conf (key, value) VALUES ('csp_extra', '"report-uri https://liberapay.report-uri.io/r/default/csp/reportOnly;"'::jsonb);
-- For local
INSERT INTO app_conf (key, value) VALUES ('csp_extra', '""'::jsonb);
