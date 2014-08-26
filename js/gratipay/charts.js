Gratipay.charts = {};


Gratipay.charts.make = function(series) {
    // Takes an array of time series data.

    if (!series.length) {
        $('.chart-wrapper').remove();
        return;
    }


    // Sort the series in increasing date order.
    // =========================================

    series.sort(function(a,b) { return a.date > b.date ? 1 : -1 });


    // Gather charts.
    // ==============
    // Sniff the first element to determine what data points are available, and
    // then search the page for chart containers matching each data point
    // variable name.

    var point  = series[0];
    var charts = [];

    for (var varname in point) {
        var chart = $('#chart_'+varname);
        if (chart.length) {
            chart.varname = varname;
            charts.push(chart);
        }
    }

    var H = $('.chart').height();
    var nweeks = series.length;
    var w = (1 / nweeks * 100).toFixed(10) + '%';

    $('.n-weeks').text(nweeks);


    // Compute maxes and scales.
    // =========================

    var maxes  = [];
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

    function Week(i, j, N, y, title) {
        var week   = $(document.createElement('div')).addClass('week');
        var shaded = $(document.createElement('div')).addClass('shaded');
        shaded.html('<span class="y-label">'+ y.toFixed() +'</span>');
        week.append(shaded);

        var xTick = $(document.createElement('span')).addClass('x-tick');
        xTick.text(i+1).attr('title', title);
        week.append(xTick);

        // Display a max flag (only once)
        if (y === maxes[j]) {
            maxes[j] = undefined;
            week.addClass('flagged');
        }

        week.css('width', w);
        shaded.css('height', y / N * H);
        return week;
    }

    for (var i=0, point; point = series[i]; i++) {
        for (var j=0, chart; chart = charts[j]; j++) {
            chart.append(
                Week(i, j, scales[j], point[chart.varname], point.date)
            );
        }
    }


    // Wire up behaviors.
    // ==================

    $('.week').click(function() {
        $(this).toggleClass('flagged');
        if ($(this).hasClass('flagged'))
            $(this).removeClass('hover');
    });

    $('.week').mouseover(function() {
        $(this).addClass('hover');
    });

    $('.week').mouseout(function() {
        $(this).removeClass('hover');
    });
};
