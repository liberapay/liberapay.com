Gittip.horn = {};

Gittip.horn.init = function()
{
    Gittip.horn.since_id = undefined;
    $('#toot-form').submit(Gittip.horn.toot);
    Gittip.horn.update({limit: 20});
};

Gittip.horn.update = function(data)
{
    clearTimeout(Gittip.horn.handle);
    data = data || {};
    if (Gittip.horn.since_id !== undefined)
        data.since_id = Gittip.horn.since_id;
    jQuery.ajax(
        { type: "GET"
        , url: "toots.json"
        , data: data
        , success: Gittip.horn.draw
         });
};

Gittip.horn.draw = function(toots)
{
    for (var i=toots.length-1, toot; toot = toots[i]; i--)
    {
        Gittip.horn.since_id = toot.id;
        Gittip.horn.drawOne(toot);
    }
    Gittip.horn.handle = setTimeout(Gittip.horn.update, 1000)
};

Gittip.horn.drawOne = function(toot)
{
    var escaped = $('<div>').text(toot.toot).html();
    var html = '<li class="'
             + (toot.horn === toot.tootee ? 'me' : 'them')
             + ' '
             + (toot.own ? 'own' : 'theirs')
             + '"><span class="toot">'
             + ( toot.tootee !== toot.horn && !toot.own
               ? 're: ' + toot.tootee + ': '
               : ''
                )
             + escaped
             + ( toot.tootee !== toot.horn && toot.own
               ? '&mdash;' + toot.tootee
               : ''
                )
             + '</div>'
             + '</span>'
             + '</li>'
    $('#toots').prepend(html)
};

Gittip.horn.success = function(data)
{
    // clear the textarea & draw any new toots
    $('#toot').val('');
    Gittip.horn.update(data);
};

Gittip.horn.toot = function(e)
{
    e.preventDefault();
    e.stopPropagation();
    var toot = $('#toot').val();

    jQuery.ajax(
        { type: "POST"
        , url: "toot.json"
        , data: {toot: toot}
        , success: Gittip.horn.success
         });
    return false;
};
