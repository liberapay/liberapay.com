drop table if exists bb404;
create temp table bb404 as (
     select e.user_name, p.username
          , p.claimed_time, p.is_suspicious, p.is_closed
          , p.balance, p.receiving, p.giving
          , p.last_bill_result, p.last_ach_result, p.paypal_email, p.bitcoin_address
       from elsewhere e
       join participants p
         on e.participant = p.username
        and e.platform = 'bitbucket'
        and e.user_name in ('AlQanneh', 'BusyRich', 'Chris---', 'D-licious', 'Thepedofile', 'UkoDragon', 'XReaper', 'Yorirou', 'albertogonzcat', 'anthony_fassett', 'antparisi', 'brettsky', 'cajetero', 'computerpunk', 'crazysim', 'danielroscaro', 'dariusc93', 'designseohosting', 'destructuring', 'dkov', 'dmmoreira', 'drumsrgr8forn8', 'dy_dx', 'earlkent', 'egeektronic', 'gkenneally', 'gobinath_mallaiyan', 'goldglovecb', 'gundead222', 'hangfromthefloor', 'hundino', 'iangrunert', 'iapc', 'igor_kh', 'jyavoc', 'k3mm0tar', 'kelevrium', 'lgorence', 'lucaspoars', 'meson3902', 'mfeher', 'mgamil', 'mhh91', 'mike_php_net', 'mstchiopstchio', 'natselection', 'omeichim', 'oppick', 'ricardotun', 'sday_atlassian', 'silasj', 'slippyd', 'spgennard', 'stickypixel', 'synekjan', 'topofthehill', 'vinitcool76', 'webindustries', 'webmanio', 'wemersonsilva', 'whats-new')

   order by p.balance desc
);
select * from bb404;
