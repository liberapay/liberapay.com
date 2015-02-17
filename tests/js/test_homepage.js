var assert = require('assert');

describe('homepage', function() {
    it('should render copy correctly', function(done) {
        browser
            .url('http://localhost:8537')
            .getText('#sidebar h1', function(err, text) {
                assert.equal(text, 'Weekly Payments');
            })
            .getText('#content h1', function(err, text) {
                assert.equal(text, 'Sign In');
            })
            .call(done);
    });
});
