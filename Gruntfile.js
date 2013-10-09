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
        immed: true,
        latedef: true,
        newcap: true,
        noarg: true,
        quotmark: true,
        sub: true,
        undef: true,
        unused: true,
        boss: true,
        eqnull: false,
        regexdash: true,
        smarttabs: false,
        strict: false,
        node: true,
        browser: true,
        jquery: true,
        devel: true,

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
