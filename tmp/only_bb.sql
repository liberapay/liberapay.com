drop table if exists only_bb;
create temp table only_bb as (
     select e1.user_name, p.username
          , p.claimed_time, p.is_suspicious, p.is_closed
          , p.balance, p.receiving, p.giving
          , p.last_bill_result, p.last_ach_result, p.paypal_email, p.bitcoin_address
       from elsewhere e1
  left join elsewhere e2
         on e1.participant = e2.participant
        and e1.platform = 'bitbucket'
        and e2.platform in ('twitter', 'github', 'facebook', 'google', 'openstreetmap')
       join participants p
         on e1.participant = p.username

      where e1.platform = 'bitbucket'
        and e2.platform is null

   order by p.balance desc
);
