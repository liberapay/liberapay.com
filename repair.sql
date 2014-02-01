update elsewhere 
set is_locked = false 
where exists (
    select * from 
    participants 
    where username=participant 
    and claimed_time is not null
) and is_locked = true;
