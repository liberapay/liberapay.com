// Jump Box on Homepage
// ====================
// "Who inspires you?"

Gittip.jump = {};

Gittip.jump.init = function() {
    function jump(e) {
        var platform = $('#jump SELECT').val().trim();
        var val = $('#jump INPUT').val().trim();
        e.preventDefault();
        e.stopPropagation();
        if (val !== '')
            window.location = '/on/' + platform + '/' + val + '/';
        return false;
    }
    $('#jump').submit(jump);
};
