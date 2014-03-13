module.exports = {

    'should strip all Unicode': function(test) {
        test.expect(2);

        test.open('http://localhost:8537')
            .execute(function() {
                this.assert.ok(window.Gittip.trim('˚aø¶') == 'a', '"˚aø¶" should become "a"');
                this.assert.ok(window.Gittip.trim('封b') == 'b', '"封b" should become "b"');
            })
            .done();
    },

    'should strip non-printable ASCII': function(test) {
        test.expect(1);

        test.open('http://localhost:8537')
            .execute(function() {
                this.assert.ok(Gittip.trim('\n\t\rc') == 'c', '"\\n\\t\\rc" should become "c"');
            })
            .done();
    },

    'should trim leading and trailing whitespace': function(test) {
        test.expect(2);

        test.open('http://localhost:8537')
            .execute(function() {
                this.assert.ok(window.Gittip.trim('  foo bar ') == 'foo bar', '"  foo bar " should become "foo bar"');
                this.assert.ok(window.Gittip.trim(' foo  bar ') == 'foo  bar', '" foo  bar " should become "foo  bar"');
            })
            .done();
    },

};
