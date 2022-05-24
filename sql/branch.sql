BEGIN;

UPDATE participants SET email_lang = 'zh' WHERE email_lang = 'zh_Hant';

UPDATE participants
   SET email_lang = email_lang || '-' || (
           SELECT lower(e.payload->'headers'->>'Cf-Ipcountry')
             FROM events e
            WHERE e.participant = participants.id
              AND e.type = 'sign_up_request'
       )
 WHERE email_lang IS NOT NULL
   AND (email_lang || '-' || (
           SELECT lower(e.payload->'headers'->>'Cf-Ipcountry')
             FROM events e
            WHERE e.participant = participants.id
              AND e.type = 'sign_up_request'
       )) IN (
           'ar-ae', 'ar-bh', 'ar-dj', 'ar-dz', 'ar-eg', 'ar-eh', 'ar-er', 'ar-il', 'ar-iq',
           'ar-jo', 'ar-km', 'ar-kw', 'ar-lb', 'ar-ly', 'ar-ma', 'ar-mr', 'ar-om', 'ar-ps',
           'ar-qa', 'ar-sa', 'ar-sd', 'ar-so', 'ar-ss', 'ar-sy', 'ar-td', 'ar-tn', 'ar-ye',
           'ca-ad', 'ca-es', 'ca-fr', 'ca-it', 'cs-cz', 'da-dk', 'da-gl', 'de-at', 'de-be',
           'de-ch', 'de-de', 'de-it', 'de-li', 'de-lu', 'el-cy', 'el-gr', 'en-ae', 'en-ag',
           'en-ai', 'en-as', 'en-at', 'en-au', 'en-bb', 'en-be', 'en-bi', 'en-bm', 'en-bs',
           'en-bw', 'en-bz', 'en-ca', 'en-cc', 'en-ch', 'en-ck', 'en-cm', 'en-cx', 'en-cy',
           'en-de', 'en-dg', 'en-dk', 'en-dm', 'en-er', 'en-fi', 'en-fj', 'en-fk', 'en-fm',
           'en-gb', 'en-gd', 'en-gg', 'en-gh', 'en-gi', 'en-gm', 'en-gu', 'en-gy', 'en-hk',
           'en-ie', 'en-il', 'en-im', 'en-in', 'en-io', 'en-je', 'en-jm', 'en-ke', 'en-ki',
           'en-kn', 'en-ky', 'en-lc', 'en-lr', 'en-ls', 'en-mg', 'en-mh', 'en-mo', 'en-mp',
           'en-ms', 'en-mt', 'en-mu', 'en-mw', 'en-my', 'en-na', 'en-nf', 'en-ng', 'en-nl',
           'en-nr', 'en-nu', 'en-nz', 'en-pg', 'en-ph', 'en-pk', 'en-pn', 'en-pr', 'en-pw',
           'en-rw', 'en-sb', 'en-sc', 'en-sd', 'en-se', 'en-sg', 'en-sh', 'en-si', 'en-sl',
           'en-ss', 'en-sx', 'en-sz', 'en-tc', 'en-tk', 'en-to', 'en-tt', 'en-tv', 'en-tz',
           'en-ug', 'en-um', 'en-us', 'en-vc', 'en-vg', 'en-vi', 'en-vu', 'en-ws', 'en-za',
           'en-zm', 'en-zw', 'es-ar', 'es-bo', 'es-br', 'es-bz', 'es-cl', 'es-co', 'es-cr',
           'es-cu', 'es-do', 'es-ea', 'es-ec', 'es-es', 'es-gq', 'es-gt', 'es-hn', 'es-ic',
           'es-mx', 'es-ni', 'es-pa', 'es-pe', 'es-ph', 'es-pr', 'es-py', 'es-sv', 'es-us',
           'es-uy', 'es-ve', 'et-ee', 'fi-fi', 'fr-be', 'fr-bf', 'fr-bi', 'fr-bj', 'fr-bl',
           'fr-ca', 'fr-cd', 'fr-cf', 'fr-cg', 'fr-ch', 'fr-ci', 'fr-cm', 'fr-dj', 'fr-dz',
           'fr-fr', 'fr-ga', 'fr-gf', 'fr-gn', 'fr-gp', 'fr-gq', 'fr-ht', 'fr-km', 'fr-lu',
           'fr-ma', 'fr-mc', 'fr-mf', 'fr-mg', 'fr-ml', 'fr-mq', 'fr-mr', 'fr-mu', 'fr-nc',
           'fr-ne', 'fr-pf', 'fr-pm', 'fr-re', 'fr-rw', 'fr-sc', 'fr-sn', 'fr-sy', 'fr-td',
           'fr-tg', 'fr-tn', 'fr-vu', 'fr-wf', 'fr-yt', 'fy-nl', 'ga-gb', 'ga-ie', 'hu-hu',
           'id-id', 'it-ch', 'it-it', 'it-sm', 'it-va', 'ja-jp', 'ko-kp', 'ko-kr', 'lt-lt',
           'lv-lv', 'ms-bn', 'ms-id', 'ms-my', 'ms-sg', 'nb-no', 'nb-sj', 'nl-aw', 'nl-be',
           'nl-bq', 'nl-cw', 'nl-nl', 'nl-sr', 'nl-sx', 'pl-pl', 'pt-ao', 'pt-br', 'pt-ch',
           'pt-cv', 'pt-gq', 'pt-gw', 'pt-lu', 'pt-mo', 'pt-mz', 'pt-pt', 'pt-st', 'pt-tl',
           'ro-md', 'ro-ro', 'ru-by', 'ru-kg', 'ru-kz', 'ru-md', 'ru-ru', 'ru-ua', 'sk-sk',
           'sl-si', 'sv-ax', 'sv-fi', 'sv-se', 'tr-cy', 'tr-tr', 'uk-ua', 'vi-vn', 'zh-cn',
           'zh-hk', 'zh-mo', 'zh-sg', 'zh-tw'
       );

UPDATE participants SET email_lang = 'zh-hans-cn' WHERE email_lang = 'zh-cn';
UPDATE participants SET email_lang = 'zh-hant-hk' WHERE email_lang = 'zh-hk';
UPDATE participants SET email_lang = 'zh-hant-mo' WHERE email_lang = 'zh-mo';
UPDATE participants SET email_lang = 'zh-hans-sg' WHERE email_lang = 'zh-sg';
UPDATE participants SET email_lang = 'zh-hant-tw' WHERE email_lang = 'zh-tw';
UPDATE participants SET email_lang = 'zh-hant' WHERE email_lang = 'zh';

END;
