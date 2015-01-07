$(document).ready(function() {
    $('#jump').submit(function (e) {
        e.preventDefault();
        e.stopPropagation();

        var platform = Gratipay.trim($('#jump select').val()),
            val      = Gratipay.trim($('#jump input').val());
        if (val) window.location = '/on/' + platform + '/' + val + '/';
    });
});
