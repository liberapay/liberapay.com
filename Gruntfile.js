var http = require('http');
var spawn = require('child_process').spawn;
var fs = require('fs');
var ini = require('ini');
var env = ini.parse(fs.readFileSync('defaults.env', 'utf8'));

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
                proxies: { '/': 'http://' + env.CANONICAL_HOST + '/' },
                files: [
                    'www/assets/jquery-1.10.2.min.js',
                    'www/assets/%version/utils.js',
                    'jstests/**/*.js',
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
    grunt.registerTask('test', ['jshint', 'gittip:start', 'karma:singlerun']);

    grunt.registerTask('gittip:start', 'Start Gittip test server (if necessary)', function gittipStart() {
        var done = this.async();

        http.get('http://' + env.CANONICAL_HOST + '/', function(res) {
            grunt.log.writeln('Gittip seems to be running already. Doing nothing.');
            done();
        })
        .on('error', function(e) {
            grunt.log.write('Starting Gittip server...');

            var started = false,
                stdout  = [],
                gittip  = spawn('make', ['run']);

            gittip.stdout.setEncoding('utf8');

            gittip.stdout.on('data', function(data) {
                if (!started && /Greetings, program! Welcome to port 8537\./.test(data)) {
                    started = true;
                    grunt.log.writeln('started.');
                    setTimeout(done, 1000);
                } else if (started && /Is something already running on port 8537/.test(data)) {
                    started = false;
                } else
                    stdout.push(data);
            });

            gittip.on('exit', function() {
                if (!started) {
                    grunt.log.writeln(stdout);
                    grunt.fail.fatal('Something went wrong when starting the Gittip server :<');
                }
            });

            process.on('exit', function() {
                gittip.kill();
            });
        });
    });
};
