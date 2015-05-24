Liberapay.charts = {};

// After retrieving the JSON data, wait for document ready event.
Liberapay.charts.make = function(series) {
    $(document).ready(function() {
        Liberapay.charts._make(series);
    });
};

Liberapay.charts._make = function(series) {
    if (!series.length) {
        $('.chart-wrapper').remove();
        return;
    }

    // Reverse the series.
    // ===================
    // For historical reasons the API is descending when we want ascending.

    series.reverse();

    // Gather charts.
    // ==============
    // Sniff the first element to determine what data points are available, and
    // then search the page for chart containers matching each data point
    // variable name.

    var charts = Object.keys(series[0]).map(function(name) {
        return $('[data-chart=' + name + ']');
    }).filter(function(c) { return c.length });


    var H = $('.chart').height() - 20;
    var W = (1 / series.length * 100).toFixed(10) + '%';


    // Compute maxes and scales.
    // =========================

    var maxes = charts.map(function(chart) {
        return series.reduce(function(previous, current) {
            return Math.max(previous, current[chart.data('chart')]);
        }, 0);
    });

    var scales = maxes.map(function(max) {
        return Math.ceil(max / 100) * 100; // round to nearest hundred
    });

    // Draw bars.
    // ==========

    charts.forEach(function(chart, chart_index) {
        series.forEach(function(point, index) {
            var y = parseFloat(point[chart.data('chart')]);
            var bar = $('<div>').addClass('bar');
            var shaded = $('<div>').addClass('shaded');
            shaded.html('<span class="y-label">'+ y.toFixed() +'</span>');
            bar.append(shaded);

            var xTick = $('<span>').addClass('x-tick');
            xTick.text(point.xText || index+1).attr('title', point.xTitle);
            bar.append(xTick);

            // Display a max flag (only once)
            if (y === maxes[chart_index] && !chart.data('max-applied')) {
                bar.addClass('flagged');
                chart.data('max-applied', true)
            }

            bar.css('width', W);

            var h = y / scales[chart_index] * H;
            if (y > 0) h = Math.max(h, 1); // make sure only true 0 is 0 height
            shaded.css('height', h);

            bar.click(function() {
                $(this).toggleClass('flagged');
            });
            chart.append(bar);
        });
    });
};
