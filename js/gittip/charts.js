Gittip.charts = {};


Gittip.subpixel_rendering_supported = function() {
    var test = $(
      '<div style="width: 200px">' +
        '<div style="float: left; width: 100.5px">a</div>' +
        '<div style="float: left; width: 100.5px">b</div>' +
      '</div>'
    ).appendTo('body');

    var children  = test.children();
    var supported = children[0].offsetTop !== children[1].offsetTop;
    test.remove();

    return supported;
}


Gittip.charts.make = function(series) {
    // Takes an array of time series data.

    if (!series.length) {
        $('.chart-wrapper').remove();
        return;
    }

    var subpixel = Gittip.subpixel_rendering_supported();


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
    var nweeks = series.length;

    var w, wstr;
    if(subpixel) {
        w    = 1 / nweeks * 100;
        wstr = w.toFixed(10) + '%';
    } else {
        w    = Math.floor(W / nweeks)
        wstr = w.toString() + 'px';
    }

    $('.n-weeks').text(nweeks);


    // Compute maxes and scales.
    // =========================

    var maxes = [];
    var scales = [];

    for (var i=0, point; point = series[i]; i++) {
        for (var j=0, chart; chart = charts[j]; j++) {
            maxes[j] = Math.max(maxes[j] || 0, point[chart.varname]);
        }
    }

    for (var i=0, len=maxes.length; i < len; i++) {
        scales.push(Math.ceil(maxes[i] / 100) * 100);
    }


    // Draw weeks.
    // ===========

    function Week(i, j, max, N, y, title) {
        var x = nweeks - i;
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
        if (y === max) {
            maxes[j] = NaN; // only show one max flag
            week.addClass('flagged');
        }

        var y = parseFloat(y);
        var h = Math.ceil(y / N * H);
        var n = nweeks - i - 1;
        week.css({
            height: H,
            width: wstr,
            left: subpixel ? 'calc('+ wstr +' * '+ n +')' : w * n
        });
        shaded.css({height: h});
        return week;
    }

    for (var i=0, point; point = series[i]; i++) {
        var point = series[i];

        for (var j=0, chart; chart = charts[j]; j++) {

            var chart = charts[j];

            chart.append(Week( i
                             , j
                             , maxes[j]
                             , scales[j]
                             , point[charts[j].varname]
                             , point.date
                              ));
        }
    }

    // Wire up behaviors.
    // ==================

    function mouseover() {
        var x = $(this).attr('x');
        var y = $(this).attr('y');

        $(this).addClass('hover');
    }

    function mouseout() {
        $(this).removeClass('hover');
    }

    $('.week').click(function() {
        $(this).toggleClass('flagged');
        if ($(this).hasClass('flagged'))
            $(this).removeClass('hover');
    });
    $('.week').mouseover(mouseover);
    $('.week').mouseout(mouseout);
};
