update paydays
set charge_fees_volume = (
    select sum(fee) 
    from exchanges 
    where timestamp > ts_start 
    and timestamp < ts_end 
    and amount > 0
);

update paydays
set ach_volume = (
    select sum(amount) 
    from exchanges 
    where timestamp > ts_start 
    and timestamp < ts_end 
    and amount < 0
);
