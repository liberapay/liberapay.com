Gratipay.charts = {};

Gratipay.charts.make = function(series) {
    $(document).ready(function() {
        Gratipay.charts._make(series);
    });
};

Gratipay.charts._make = function(series) {
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

    Object.keys(point).forEach(function(varname) {
        var chart = $('#chart_'+varname);
        if (chart.length) {
            chart.varname = varname;
            charts.push(chart);
        }
    });

    var flagRoom = 20;
    var H = $('.chart').height() - flagRoom;
    var nitems = series.length;
    var w = (1 / nitems * 100).toFixed(10) + '%';


    // Compute maxes and scales.
    // =========================

    var maxes = charts.map(function(chart) {
        return series.reduce(function(previous, current) {
            return Math.max(previous, current[chart.varname]);
        }, 0);
    });

    var scales = maxes.map(function(max) {
        return Math.ceil(max / 100) * 100; // round to nearest hundred
    });

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
        var h = Math.ceil(yParsed / N * H);
        shaded.css('height', h)

        bar.click(function() {
            $(this).toggleClass('flagged');
        });
        return bar;
    }

    for (var i=0, point; point = series[i]; i++) {
        for (var j=0, chart; chart = charts[j]; j++) {
            var xText = point.xText || i+1;
            var xTitle = point.xTitle || '';
            chart.append(Bar(i, j, scales[j], point[chart.varname], xText, xTitle));
        }
    }
};
