Gittip.upgrade = {};

Gittip.upgrade.init = function () {

    var userAgent = navigator.userAgent.toLowerCase();
    var browser = (userAgent.indexOf('msie') != -1) ? parseInt(userAgent.split('msie')[1]) : -1;

    if(browser != -1 && browser < 9) {
        var message = '' +
            '<div id="upgrade_browser">' +
            '   <div class="container">' +
            'This browser isn\'t supported by GitTip.com. ' +
            'We encourage You to upgrade or change browser. ' +
            '<a href="http://browsehappy.com">Learn more</a>' +
            '   </div>' +
            '</div>';
        $("body").prepend(message);
    }
};

$(document).ready(Gittip.upgrade.init);