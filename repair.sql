update paydays
set charge_fees_volume = (
    select coalesce(sum(fee), 0)
    from exchanges 
    where timestamp > ts_start 
    and timestamp < ts_end 
    and amount > 0
);

update paydays
set ach_volume = (
    select coalesce(sum(amount), 0)
    from exchanges 
    where timestamp > ts_start 
    and timestamp < ts_end 
    and amount < 0
);
