describe('Gittip.trim', function() {
    it('should strip all Unicode', function() {
        Gittip.trim('˚aø¶').should.equal('a');
        Gittip.trim('封b').should.equal('b');
    });
    it('should strip non-printable ASCII', function() {
        Gittip.trim('\n\t\rc').should.equal('c');
    });
    it('should trim leading and trailing whitespace', function() {
        Gittip.trim('  foo bar ').should.equal('foo bar')
        Gittip.trim(' foo  bar ').should.equal('foo  bar')
    });
});
