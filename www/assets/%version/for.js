Gittip.for = {}

Gittip.for.success = function(d)
{
    var UL = document.createElement('UL');
    for (var i=0, item; item = d[i]; i++)
    {
        username = item[0];
        id = item[1];

        console.log(username, id);
    }
};

Gittip.for.reload = function(d)
{
    var query = $('#deserts input').val();
    if (query.length < 2)
        return;
    jQuery.ajax(
        { url: '/for/_lookup.json'
        , data: {query: query}
        , success: Gittip.for.success
         }
    )
};

Gittip.for.init = function()
{
    $('#deserts input').keyup(Gittip.for.reload)
};
