module.exports = {

    'Copy should render correctly': function(test) {
        test.expect(2);

        test.open('http://localhost:8537')
            .assert.text('h2.top span').is('Sustainable Crowdfunding')
            .assert.text('h1 span').is('Inspiring Generosity')
            .done();
    },

    'Jump Box (Who inspires you?)': function(test) {
        test.expect(1);

        test.open('http://localhost:8537')
            .type('#jump input', '˚aø¶')
            .submit('#jump')
            .assert.url().is('http://localhost:8537/on/twitter/a/')
            .done();
    },

    //'should strip leading and trailing whitespace before submitting': function(test) {},
    //'should let you search for users through their connected accounts': function(test) {},

};
