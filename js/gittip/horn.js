Gittip.horn = {};

Gittip.horn.init = function() {
    Gittip.horn.since_id = undefined;
    $('#toot-form').submit(Gittip.horn.toot);
    Gittip.horn.update({limit: 20});


    $('#toot')
        // setup toot button logic
        // 141 because the easy counter plugin is strange
        .keyup(function () {
            $('#toot-button').attr('disabled', $(this).val().length === 0 || $(this).val().length > 141);
        })
        // setup character coutner
        .jqEasyCounter({
            maxChars: 140,
            maxCharsWarning: 125,
            msgWarnColor: '#f00',
            msgAppendMethod: 'insertBefore'
        });
};

Gittip.horn.update = function(data) {
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

Gittip.horn.draw = function(toots) {
    for (var i=toots.length-1, toot; toot = toots[i]; i--) {
        Gittip.horn.since_id = toot.id;
        Gittip.horn.drawOne(toot);
    }
    Gittip.horn.handle = setTimeout(Gittip.horn.update, 10000);
};

Gittip.horn.drawOne = function(toot) {
    var escaped = $('<div>').text(toot.toot).html();
    var TOOTER = '<a href="/' + toot.tooter + '/">' + toot.tooter + '</a>';
    var TOOTEE = '<a href="/' + toot.tootee + '/">' + toot.tootee + '</a>';
    var html = '<li class="box ' +
               (toot.horn === toot.tootee ? 'me' : 'them') +
               ' ' +
               (toot.tooter_is_tootee ? 'own' : 'theirs') +
               '"><div class="toot word-wrap">' + escaped + '</div>' +
               '<div class="nav level-1">' +

             /* [someone] tooted [someone]'s horn
              *
              * alice     tooted their own   horn
              * alice     tooted your        horn
              * alice     tooted bob      's horn
              * You       tooted your own    horn
              * You       tooted bob      's horn
              *
              */

               ( toot.user_is_tooter ? 'You' : TOOTER) +
               ' tooted ' +
               ( toot.user_is_tootee ?
                 (toot.user_is_tooter ? 'your own' : 'your') :
                 (toot.tooter_is_tootee ? 'their own' : TOOTEE + "'s")
                ) +
               ' horn</div>' +
               '</li>';
    $('#toots').prepend(html);
};

Gittip.horn.success = function(data) {
    // clear the textarea & draw any new toots
    $('#toot').val('');
    Gittip.horn.update(data);
};

Gittip.horn.error = function () {
    // temp alert for failure
    alert('Failed to save toot. :(');
};

Gittip.horn.toot = function(e) {
    e.preventDefault();
    e.stopPropagation();
    var toot = $('#toot').val();

    jQuery.ajax(
        { type: "POST"
        , url: "toot.json"
        , data: {toot: toot}
        , success: Gittip.horn.success
        , error: Gittip.horn.error
         });
    return false;
};
