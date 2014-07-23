Gittip.upgrade = {};

Gittip.upgrade.init = function () {

    var userAgent = navigator.userAgent.toLowerCase();
    var browser = (userAgent.indexOf('msie') != -1) ? parseInt(userAgent.split('msie')[1], 10) : -1;

    if(browser != -1 && browser < 9) {
        var message = '' +
            '<div id="upgrade_browser">' +
            '   <div class="container">' +
            'You\'re using a browser that we don\'t support. ' +
            'We encourage you to <a href="http://browsehappy.com/">upgrade</a>.' +
            '   </div>' +
            '</div>';
        $("body").prepend(message);
    }
};

$(document).ready(Gittip.upgrade.init);
