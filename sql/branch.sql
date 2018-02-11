SELECT 'after deployment';

UPDATE participants
   SET email_lang = (
           SELECT l
             FROM ( SELECT regexp_replace(x, '[-;].*', '') AS l
                      FROM regexp_split_to_table(email_lang, ',') x
                  ) x
            WHERE l IN ('ca', 'cs', 'da', 'de', 'el', 'en', 'eo', 'es', 'et', 'fi',
                        'fr', 'fy', 'hu', 'id', 'it', 'ja', 'ko', 'nb', 'nl', 'pl',
                        'pt', 'ru', 'sl', 'sv', 'tr', 'uk', 'zh')
            LIMIT 1
       )
 WHERE length(email_lang) > 0;
