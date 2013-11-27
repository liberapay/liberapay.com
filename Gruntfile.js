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
                tasks: ['jshint:js', 'karma:tests:run']
            },

            tests: {
                files: '<%= jshint.tests %>',
                tasks: ['jshint:tests', 'karma:tests:run']
            }
        },

        jshint: {
            gruntfile: 'Gruntfile.js',
            js: 'js/**/*.{js,json}',
            tests: 'jstests/**/*.js',

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
        },

        karma: {
            tests: {
                hostname: '0.0.0.0'
            },

            singlerun: {
                singleRun: true
            },

            options: {
                browsers: ['PhantomJS'],
                reporters: 'dots',
                frameworks: ['mocha', 'browserify'],
                urlRoot: '/karma/',
                proxies: { '/': 'http://127.0.0.1:8537/' },
                files: [
                    'www/assets/jquery-1.8.3.min.js',
                    'www/assets/%version/utils.js',
                    'jstests/**/test_*.js',
                ],

                browserify: { watch: true },
                preprocessors: {
                    'jstests/**/*.js': ['browserify']
                }
            }
        }
    });

    grunt.loadNpmTasks('grunt-contrib-jshint');
    grunt.loadNpmTasks('grunt-contrib-watch');
    grunt.loadNpmTasks('grunt-karma');

    grunt.registerTask('default', ['test']);
    grunt.registerTask('test', ['jshint', 'karma:singlerun']);
};
