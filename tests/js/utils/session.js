var exec = require('sync-exec');

module.exports = function createSession(user) {
    return exec(
        './env/bin/honcho -e defaults.env,tests/test.env,tests/local.env ' +
        'run ./env/bin/python ./tests/js/utils/auth-helper.py ' + user
    ).stdout.slice(0, -1);
};
