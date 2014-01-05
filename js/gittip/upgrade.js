Gittip.upgrade = {};

Gittip.upgrade.init = function () {

    var browserSupport = new Gittip.upgrade.BrowserSupport();
    browserSupport.isSupportedBrowser();
};

Gittip.upgrade.BrowserSupport = function () {
    this.userAgent = navigator.userAgent.toLowerCase();
}

Gittip.upgrade.BrowserSupport.prototype = {
    /*
    If method return -1 then this isn't IE browser.
    Also this work only to IE10. IE 11 has different user agent. (notice for future for gittip)
     */
    detectIEVersion: function () {
        return (this.userAgent.indexOf('msie') != -1) ? parseInt(this.userAgent.split('msie')[1]) : -1;
    },

    detectBrowser: function () {
        this.browser = this.detectIEVersion();
    },

    isSupportedBrowser: function () {
        this.detectBrowser()
        // is this old IE?
        if(this.browser != -1 && this.browser < 9){
            this.showMessage();
        }
    },

    showMessage: function () {
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
}

$(document).ready(Gittip.upgrade.init);