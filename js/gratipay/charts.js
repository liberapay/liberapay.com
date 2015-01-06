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
    var nitems = series.length;
    var w = (1 / nitems * 100).toFixed(10) + '%';


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


    // Draw bars.
    // ==========

    function Bar(i, j, N, y, title) {
        var bar = $(document.createElement('div')).addClass('bar');
        var shaded = $(document.createElement('div')).addClass('shaded');
        shaded.html('<span class="y-label">'+ y.toFixed() +'</span>');
        bar.append(shaded);

        var xTick = $(document.createElement('span')).addClass('x-tick');
        xTick.text(i+1).attr('title', title);
        bar.append(xTick);

        // Display a max flag (only once)
        if (y === maxes[j]) {
            maxes[j] = undefined;
            bar.addClass('flagged');
        }

        bar.css('width', w);
        shaded.css('height', y / N * H);
        return bar;
    }

    for (var i=0, point; point = series[i]; i++) {
        for (var j=0, chart; chart = charts[j]; j++) {
            chart.append(
                Bar(i, j, scales[j], point[chart.varname], point.date)
            );
        }
    }


    // Wire up behaviors.
    // ==================

    $('.bar').click(function() {
        $(this).toggleClass('flagged');
        if ($(this).hasClass('flagged'))
            $(this).removeClass('hover');
    });

    $('.bar').mouseover(function() {
        $(this).addClass('hover');
    });

    $('.bar').mouseout(function() {
        $(this).removeClass('hover');
    });
};
