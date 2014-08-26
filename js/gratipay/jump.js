// Jump Box on Homepage
// ====================
// "Who inspires you?"

Gratipay.jump = {};

Gratipay.jump.init = function() {
    function jump(e) {
        e.preventDefault();
        e.stopPropagation();

        var platform = Gratipay.trim($('#jump select').val()),
            val      = Gratipay.trim($('#jump input').val());
        if (val)
            window.location = '/on/' + platform + '/' + val + '/';
    }
    $('#jump').submit(jump);
};
