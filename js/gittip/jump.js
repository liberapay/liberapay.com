// Jump Box on Homepage
// ====================
// "Who inspires you?"

Gittip.jump = {};

Gittip.jump.init = function() {
    function jump(e) {
        e.preventDefault();
        e.stopPropagation();

        var platform = Gittip.trim($('#jump select').val()),
            val      = Gittip.trim($('#jump input').val());
        if (val)
            window.location = '/on/' + platform + '/' + val + '/';
    }
    $('#jump').submit(jump);
};
