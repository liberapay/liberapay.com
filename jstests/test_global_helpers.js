var should = require('should');

describe('Test the global helper functions', function () {

    it('should mock console if it is not supported by the browser', function () {
        // Test that the mocked console has all the functions we would
        // expect it to have.

        // mock_console is executed on load so we need to clear console first.
        window.console = null;
        mock_console();

        should(console).not.equal(null);

        var consoleCmds = ['log', 'debug', 'info', 'warn', 'error', 'assert', 'dir',
            'dirxml', 'group', 'groupEnd', 'time', 'timeEnd', 'count',
            'trace', 'profile', 'profileEnd'];

        // Ensure real list is the same length as our test list. If the real
        // list contains more items we should be testing for those too.
        Object.keys(console).length .should.be.exactly(consoleCmds.length);

        // Check there are no missing items.
        console.should.have.keys(consoleCmds);
    });

});
