var assert = require('assert');
var createSession = require('./_session.js');

describe('authed homepage', function() {
    beforeEach(function(done) {
        browser
            .url('http://localhost:8537')
            .setCookie({
                name: 'session',
                value: createSession('alice')
            })
            .call(done);
    });

    afterEach(function(done) {
        browser
            .url('http://localhost:8537')
            .deleteCookie('session')
            .call(done);
    });

    it('should render copy correctly', function(done) {
        browser
            .url('http://localhost:8537')
            .getText('.greeting h1', function(err, text) {
                assert.equal(text, 'Welcome back, alice!');
            })
            .getText('.greeting p:first-of-type', function(err, text) {
                assert.equal(text, 'Your balance is $0.00.');
            })
            .deleteCookie('session')
            .call(done);
    });
});
