module.exports = {

    'Copy should render correctly': function(test) {
        test.expect(2);

        test.open('http://localhost:8537')
            .assert.text('.pitch h1').is('Weekly Payments')
            .assert.text('.action h1').is('Sign In')
            .done();
    },

};
