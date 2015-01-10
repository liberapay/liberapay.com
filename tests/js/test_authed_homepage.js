var assert = require('assert');
var createSession = require('./utils/session.js');

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
            .getText('#content h1', function(err, text) {
                assert.equal(text, 'Welcome, alice!');
            })
            .deleteCookie('session')
            .call(done);
    });
});
