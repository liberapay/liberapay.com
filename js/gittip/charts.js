Gittip.charts = {};

Gittip.charts.make = function(series) {
    // Takes an array of time series data.

    if (!series.length) {
        $('.chart-wrapper').remove();
        return;
    }


    // Gather charts.
    // ==============
    // We find charts based on the variable names from the first element in the
    // time series.

    var first = series[0];
    var charts = [];

    for (var varname in first) {
        var chart = $('#chart_'+varname);
        if (chart.length) {
            chart.varname = varname;
            charts.push(chart);
        }
    }

    var H = $('.chart').height();
    var W = $('.chart').width();
    var nweeks = series.length; // don't show Gittip #0
    var w = Math.floor((W - 20) / nweeks);
    var W = w * nweeks;

    $('.n-weeks').text(nweeks);
    $('.chart').width(W);


    // Compute maxes and scales.
    // =========================

    var maxes = [];
    var scales = [];

    for (var i=0, point; point = series[i]; i++) {
        for (var j=0, chart; chart = charts[j]; j++) {
            maxes[j] = Math.max(maxes[j] || 0, point[chart.varname]);
        }
        /*
        maxCumulative += parseFloat(point.transfer_volume);
        */
    }

    for (var i=0, len=maxes.length; i < len; i++) {
        scales.push(Math.ceil(maxes[i] / 100) * 100);
    }


    // Draw weeks.
    // ===========

    function Week(n, max, N, y, title)
    {
        var x = nweeks - n;
        var create = function(x) { return document.createElement(x); };
        var week = $(create('div')).addClass('week');
        var shaded = $(create('div')).addClass('shaded');
        shaded.html( '<span class="y-label">'
                   + parseInt(y, 10)
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

    //var cumulative = maxCumulative;
    for (var i=0, point; point = series[i]; i++)
    {
        var point = series[i];

        for (var j=0, chart; chart = charts[j]; j++) {

            var chart = charts[j];

            chart.append(Week( i
                             , maxes[j]
                             , scales[j]
                             , point[charts[j].varname]
                             , point.date
                              ));
            /*
            Cumulative.append(Week( i
                                  , maxCumulative
                                  , scaleCumulative
                                  , cumulative
                                  , weekstamp
                                   ));
            cumulative -= parseFloat(point.transfer_volume);
            */
        }
    }

    $('.week').width(w);
    $('.shaded').width(w);


    // Wire up behaviors.
    // ==================

    function mouseover()
    {
        var x = $(this).attr('x');
        var y = $(this).attr('y');

        $(this).addClass('hover');
    }

    function mouseout()
    {
        $(this).removeClass('hover');
    }

    $('.week').click(function()
    {
        $(this).toggleClass('flagged');
        if ($(this).hasClass('flagged'))
            $(this).removeClass('hover');
    });
    $('.week').mouseover(mouseover);
    $('.week').mouseout(mouseout);
};
