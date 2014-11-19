var assert = require('assert');

describe('Gratipay.trim()', function() {

    it('should strip all unicode', function(done) {
        browser
            .url('http://localhost:8537')
            .execute(
                function() {
                    return {
                        a: window.Gratipay.trim('˚aø¶'),
                        b: window.Gratipay.trim('封b'),
                    };
                },
                function(err, res) {
                    assert.equal(res.value.a, 'a', '"˚aø¶" should become "a"');
                    assert.equal(res.value.b, 'b', '"封b" should become "b"');
                }
            )
            .call(done);
    });

    it('should strip non-printable ASCII', function(done) {
        browser
            .url('http://localhost:8537')
            .execute(
                function() {
                    return {
                        c: Gratipay.trim('\n\t\rc')
                    };
                },
                function(err, res) {
                    assert.equal(res.value.c, 'c', '"\\n\\t\\rc" should become "c"');
                }
            )
            .call(done);
    });

    it('should trim leading and trailing whitespace', function(done) {
        browser
            .url('http://localhost:8537')
            .execute(
                function() {
                    return [
                        window.Gratipay.trim('  foo bar '),
                        window.Gratipay.trim(' foo  bar ')
                    ];
                },

                function(err, res) {
                    assert.equal(res.value[0], 'foo bar', '"  foo bar " should become "foo bar"');
                    assert.equal(res.value[1], 'foo  bar', '" foo  bar " should become "foo  bar"');
                }
            )
            .call(done);
    });
});
