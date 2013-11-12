Gittip.Chart = function() {

    var Withdrawals = $('#withdrawals-');
    var Charges = $('#charges-');
    var Volume = $('#volume-');
    var Cumulative = $('#cumulative-');
    var Users = $('#users-');
    var Active = $('#active-');

    function mouseover()
    {
        var x = $(this).attr('x');
        var y = $(this).attr('y');

        $(this).addClass('hover');
    }

    function mouseout()
    {
        $(this).removeClass('hover')
    }

    jQuery.get('/about/paydays.json', function(paydays)
    {
        var H = $('.chart').height();
        var W = $('.chart').width();
        var nweeks = paydays.length - 1; // don't show Gittip #0
        var w = Math.floor((W - 20) / nweeks);
        var W = w * nweeks;

        var payday = null;

        $('.n-weeks').text(nweeks);
        $('.chart').width(W);


        // Compute vertical scale.
        // =======================

        var maxUsers = 0;
        var maxActive = 0;
        var maxGifts = 0;
        var maxCumulative = 0;
        var maxWithdrawals = 0;
        var maxCharges = 0;


        for (var i=0; i < nweeks; i++)
        {
            payday = paydays[i];
            maxUsers = Math.max( maxUsers
                               , parseFloat(payday.nparticipants)
                                );
            maxActive = Math.max( maxActive
                                , parseFloat(payday.nactive)
                                 );
            maxCumulative += parseFloat(payday.transfer_volume);
            maxGifts = Math.max( maxGifts
                               , parseFloat(payday.transfer_volume)
                                );
            maxWithdrawals = Math.max( maxWithdrawals
                                     , -parseFloat(payday.ach_volume)
                                      );
            maxCharges = Math.max( maxCharges
                                 , parseFloat(payday.charge_volume)
                                  );
        }

        scaleUsers = Math.ceil(maxUsers / 100) * 100;
        scaleActive = Math.ceil(maxActive / 100) * 100;
        scaleGifts = Math.ceil(maxGifts / 100) * 100;
        scaleCumulative = Math.ceil(maxCumulative / 100) * 100;
        scaleWithdrawals = Math.ceil(maxWithdrawals / 100) * 100;
        scaleCharges = Math.ceil(maxCharges / 100) * 100;


        // Draw weeks.
        // ===========

        function Week(n, max, N, y, title)
        {
            var x = nweeks - n;
            var create = function(x) { return document.createElement(x) };
            var week = $(create('div')).addClass('week');
            var shaded = $(create('div')).addClass('shaded');
            shaded.html( '<span class="y-label">'
                       + parseInt(y)
                       + '</span>'
                        );
            week.append(shaded);
            week.attr({x: x, y: y});

            var xTick = $(create('span')).addClass('x-tick');
            xTick.text(x);
            xTick.attr('title', title);
            if ((x % 5) === 0)
                xTick.addClass('on');
            week.append(xTick);
            if (y === max)
                week.addClass('flagged');

            var y = parseFloat(y);
            var h = Math.ceil(((y / N) * H));
            week.height(H);
            week.width(w);
            week.css({"left": w * (nweeks - n - 1)});
            shaded.css({"height": h});
            return week;
        }

        var cumulative = maxCumulative;
        for (var i=0; i < nweeks; i++)
        {
            var payday = paydays[i];
            var weekstamp = payday.ts_start.slice(0, 10);

            Users.append(Week( i
                             , maxUsers
                             , scaleUsers
                             , payday.nparticipants
                             , weekstamp
                              ));
            Active.append(Week( i
                              , maxActive
                              , scaleActive
                              , payday.nactive
                              , weekstamp
                               ));
            Volume.append(Week( i
                              , maxGifts
                              , scaleGifts
                              , payday.transfer_volume
                              , weekstamp
                               ));
            Cumulative.append(Week( i
                                  , maxCumulative
                                  , scaleCumulative
                                  , cumulative
                                  , weekstamp
                                   ));
            cumulative -= parseFloat(payday.transfer_volume);
            Withdrawals.append(Week( i
                                   , maxWithdrawals
                                   , scaleWithdrawals
                                   , -payday.ach_volume
                                   , weekstamp
                                    ));
            Charges.append(Week( i
                               , maxCharges
                               , scaleCharges
                               , payday.charge_volume
                               , weekstamp
                                ));
        }

        $('.week').width(w);
        $('.shaded').width(w);


        // Wire up behaviors.
        // ==================

        $('.week').click(function()
        {
            $(this).toggleClass('flagged');
            if ($(this).hasClass('flagged'))
                $(this).removeClass('hover');
        });
        $('.week').mouseover(mouseover)
        $('.week').mouseout(mouseout)
    });
};
