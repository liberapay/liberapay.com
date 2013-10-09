module.exports = function(grunt) {
  'use strict';

  grunt.initConfig({
    pkg: grunt.file.readJSON('package.json'),

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

        globals: {
          Gittip: true,
          _gttp: true,
          jQuery: true,
          $: true,
          mixpanel: true
        }
      }
    }
  });

  grunt.loadNpmTasks('grunt-contrib-jshint');

  grunt.registerTask('default', ['test']);
  grunt.registerTask('test', ['jshint']);
};
