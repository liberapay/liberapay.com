$(document).ready(function() {
    $('#jump').submit(function (e) {
        e.preventDefault();
        e.stopPropagation();

        var platform = Liberapay.trim($('#jump select').val()),
            val      = Liberapay.trim($('#jump input').val());
        if (val) window.location = '/on/' + platform + '/' + val + '/';
    });
});
