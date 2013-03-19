basePath = '';

files = [
  ANGULAR_SCENARIO,
  ANGULAR_SCENARIO_ADAPTER,

  'jstests/e2e/*.js'
];

proxies = {
  '/': 'http://localhost:8537/'
};

browsers = ['PhantomJS'];

autoWatch = false;

singleRun = true;

reporters = ['progress'];
