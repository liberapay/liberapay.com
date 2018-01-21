Liberapay.charts = {};

Liberapay.charts.init = function() {
    $('[data-charts]').click(function() {
        this.disabled = true;
        Liberapay.charts.load($(this).data('charts'), this);
    });
    $('[data-charts-autoload]').each(function() {
        Liberapay.charts.load($(this).data('charts-autoload'));
    });
}

Liberapay.charts.load = function(url, button) {
    jQuery.get(url, function(series) {
        $(function() {
            Liberapay.charts.make(series, button);
        });
    }).fail(Liberapay.error);
}

Liberapay.charts.make = function(series, button) {
    if (series.length) {
        $('.chart-wrapper').show();
    } else if (button && $(button).data('msg-empty')) {
        var $btn = $(button);
        $btn.attr('disabled', '').prop('disabled');
        $btn.after($('<span>').text(' '+$btn.data('msg-empty')));
        return;
    } else {
        return;
    }

    function parsePoint(o) {
        return parseFloat(o.amount || o);
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
    var W = (1 / series.length).toFixed(10) * $('.chart').width();
    var skip = 0;
    if (W < 5) {
        var keep = Math.floor($('.chart').width() / 5);
        skip = series.length - keep;
        series = series.slice(-keep);
    }
    W = W > 10 ? '10px' : (W < 5 ? '5px' : Math.floor(W)+'px');


    // Compute maxes and scales.
    // =========================

    var maxes = charts.map(function(chart) {
        return series.reduce(function(previous, current) {
            return Math.max(previous, parsePoint(current[chart.data('chart')]));
        }, 0);
    });

    var scales = maxes.map(function(max) {
        return Math.ceil(max / 100) * 100; // round to nearest hundred
    });

    // Draw bars.
    // ==========

    charts.forEach(function(chart, chart_index) {
        chart.css('min-width', (series.length * 5) + 'px');
        series.forEach(function(point, index) {
            var y = parsePoint(point[chart.data('chart')]);
            var bar = $('<div>').addClass('bar');
            var shaded = $('<div>').addClass('shaded');
            shaded.html('<span class="y-label">'+ y.toFixed() +'</span>');
            bar.append(shaded);

            var xTick = $('<span>').addClass('x-tick');
            xTick.text(point.xText || index+skip+1).attr('title', point.xTitle);
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
