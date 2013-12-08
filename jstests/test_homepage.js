var should = require('should');

var $body, $iframe = $('<iframe/>').appendTo('body');
describe('Test the homepage', function () {

    beforeEach(function (done) {
        $iframe.attr('src', '/')
            .one('load', function() {
                $body = $(this.contentDocument.body);
                done();
            });
    });

    it('should render copy correctly', function () {
        $body.find('h2.top span').text().should.contain('Sustainable Crowdfunding');
        $body.find('h1 span').text().should.contain('Inspiring Generosity');
    });

});
