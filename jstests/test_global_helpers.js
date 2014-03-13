module.exports = {

    'should mock console if it is not supported by the browser': function(test) {
        test.expect(3);

        test.open('http://localhost:8537')
            .execute(function() {
                // Test that the mocked console has all the functions we would
                // expect it to have.

                // mock_console is executed on load so we need to clear console first.
                window.console = null;
                mock_console();

                this.assert.ok(console !== null, 'console should not be null');

                var consoleCmds = ['log', 'debug', 'info', 'warn', 'error', 'assert', 'dir',
                    'dirxml', 'group', 'groupEnd', 'time', 'timeEnd', 'count',
                    'trace', 'profile', 'profileEnd'];

                // Ensure real list is the same length as our test list. If the real
                // list contains more items we should be testing for those too.
                this.assert.ok(
                    Object.keys(console).length == consoleCmds.length,
                    'console should have a key length of ' + consoleCmds.length
                );

                // Check there are no missing items.
                var missing = false;
                consoleCmds.forEach(function(key) {
                    if (typeof console[key] == 'undefined')
                        missing = true;
                });

                this.assert.ok(!missing, 'no items should be missing from console');
            })
            .done();
    },

};
