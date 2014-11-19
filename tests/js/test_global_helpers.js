var assert = require('assert');

describe('global helpers', function() {
    it('should mock console if it is not supported by the browser', function(done) {
        browser
            .url('http://localhost:8537')
            .execute(
                function() {
                    // Since console will already exist, we'll need to clear it
                    // before calling `mock_console()`
                    window.console = null;
                    mock_console();

                    return window.console;
                },

                function(err, res) {
                    var cons = res.value;

                    // Test that the mocked console has all the functions we
                    // would expect it to have.

                    assert(cons !== null, 'cons should not be null');

                    var consCmds = ['log', 'debug', 'info', 'warn', 'error',
                        'assert', 'dir', 'dirxml', 'group', 'groupEnd', 'time',
                        'timeEnd', 'count', 'trace', 'profile', 'profileEnd'];

                    // Ensure real list is the same length as our test list. If
                    // the real list contains more items we should be testing
                    // for those too.
                    assert(
                        Object.keys(cons).length == consCmds.length,
                        'cons should have a key length of ' + consCmds.length
                    );

                    // Check there are no missing items.
                    var missing = false;
                    consCmds.forEach(function(key) {
                        if (typeof cons[key] == 'undefined')
                            missing = true;
                    });

                    assert(!missing, 'no items should be missing from console');
                }
            )
            .call(done);
    });
});
