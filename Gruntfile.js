module.exports = function(grunt) {
    'use strict';

    grunt.initConfig({
        pkg: grunt.file.readJSON('package.json'),

        watch: {
            gruntfile: {
                files: '<%= jshint.gruntfile %>',
                tasks: 'jshint:gruntfile'
            },

            js: {
                files: '<%= jshint.js %>',
                tasks: 'jshint:js'
            }
        },

        jshint: {
            gruntfile: 'Gruntfile.js',
            js: 'js/**/*.{js,json}',

            options: {
                jshintrc: '.jshintrc',

                globals: {
                    Gittip: true,
                    _gttp: true,
                    gttpURI: true,
                    mixpanel: true,
                    alert: true
                }
            }
        }
    });

    grunt.loadNpmTasks('grunt-contrib-jshint');
    grunt.loadNpmTasks('grunt-contrib-watch');

    grunt.registerTask('default', ['test']);
    grunt.registerTask('test', ['jshint']);
};
