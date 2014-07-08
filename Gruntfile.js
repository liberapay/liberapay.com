var http = require('http');
var spawn = require('child_process').spawn;
var fs = require('fs');
var ini = require('ini');
var yaml = require('js-yaml');

module.exports = function(grunt) {
    'use strict';

    grunt.initConfig({
        pkg: grunt.file.readJSON('package.json'),

        env: ini.parse(
            fs.readFileSync('defaults.env', 'utf8') +
            fs.readFileSync('tests/test.env', 'utf8') +
            (fs.existsSync('tests/local.env') ?
                fs.readFileSync('tests/local.env', 'utf8') : '')
        ),

        watch: {
            gruntfile: {
                files: '<%= jshint.gruntfile %>',
                tasks: 'jshint:gruntfile'
            },

            js: {
                files: '<%= jshint.js %>',
                tasks: ['jshint:js', 'dalek']
            },

            tests: {
                files: '<%= jshint.tests %>',
                tasks: ['jshint:tests', 'dalek']
            }
        },

        jshint: {
            gruntfile: 'Gruntfile.js',
            js: 'js/**/*.{js,json}',
            tests: 'tests/js/**/*.js',

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

        dalek: {
            tests: 'tests/js/**/test_*.js'
        }
    });

    grunt.loadNpmTasks('grunt-contrib-jshint');
    grunt.loadNpmTasks('grunt-contrib-watch');
    grunt.loadNpmTasks('grunt-dalek');

    grunt.registerTask('default', ['test']);
    grunt.registerTask('test', ['jshint', 'aspen:start', 'dalek']);

    grunt.registerTask('aspen:start', 'Start Aspen (if necessary)', function aspenStart() {
        var done = this.async();

        grunt.config.requires('env.CANONICAL_HOST');
        var canonicalHost = grunt.config.get('env.CANONICAL_HOST') || 'localhost:8537';

        http.get('http://' + canonicalHost + '/', function(res) {
            grunt.log.writeln('Aspen seems to be running already. Doing nothing.');
            done();
        })
        .on('error', function(e) {
            grunt.log.write('Starting Aspen...');

            var started = false;
            var aspen_out = [];

            var bin = 'env/' + (process.platform == 'win32' ? 'Scripts' : 'bin');
            var child = spawn(bin+'/honcho', ['run', 'web'], {
                env: grunt.config.get('env')
            });

            child.stdout.setEncoding('utf8');
            child.stderr.setEncoding('utf8');

            child.stdout.on('data', function(data) {
                aspen_out.push(data);

                if (!started && /Greetings, program! Welcome to port \d+\./.test(data)) {
                    started = true;
                    grunt.log.writeln(' started.');
                    setTimeout(done, 1000);
                } else if (started && /Is something already running on port \d+/.test(data)) {
                    started = false;
                }
            });

            child.stderr.on('data', function(data) { aspen_out.push(data); });

            child.on('exit', function() {
                if (!started) {
                    grunt.log.writeln(' failed!');
                    grunt.log.write(aspen_out);
                    grunt.fail.fatal('Something went wrong when starting Aspen :<');
                }
            });

            process.on('exit', function() {
                child.kill();
            });
        });
    });
};
