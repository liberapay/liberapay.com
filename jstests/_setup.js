iframe = $('<iframe/>').appendTo('body');

before(function(done) {
    this.timeout(10000);
    iframe.attr('src', '/').one('load', function() {
        body = $(this.contentDocument.body);
        Gittip = this.contentWindow.Gittip;
        done();
    });
});
