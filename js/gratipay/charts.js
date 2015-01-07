Gratipay.charts = {};


Gratipay.charts.make = function(series) {
    // Takes an array of data points.

    if (!series.length) {
        $('.chart-wrapper').remove();
        return;
    }


    // Reverse the series.
    // ===================
    // For historical reasons it comes to us in the opposite order from what we
    // want.

    series.reverse();


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

    var flagRoom = 20;
    var H = $('.chart').height() - flagRoom;
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

    function Bar(i, j, N, y, xText, xTitle) {
        var yParsed = parseFloat(y);
        var bar = $('<div>').addClass('bar');
        var shaded = $('<div>').addClass('shaded');
        shaded.html('<span class="y-label">'+ yParsed.toFixed() +'</span>');
        bar.append(shaded);

        var xTick = $('<span>').addClass('x-tick');
        xTick.text(xText).attr('title', xTitle);
        bar.append(xTick);

        // Display a max flag (only once)
        if (yParsed === maxes[j]) {
            maxes[j] = undefined;
            bar.addClass('flagged');
        }

        bar.css('width', w);
        var h = yParsed / N * H;
        if (yParsed > 0) h = Math.max(h, 1); // make sure only true 0 is 0 height
        shaded.css('height', h)
        return bar;
    }

    for (var i=0, point; point = series[i]; i++) {
        for (var j=0, chart; chart = charts[j]; j++) {
            var xText = point.xText || i+1;
            var xTitle = point.xTitle || '';
            chart.append(Bar(i, j, scales[j], point[chart.varname], xText, xTitle));
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
