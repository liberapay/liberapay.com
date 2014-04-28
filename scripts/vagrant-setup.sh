#!/usr/bin/env bash

set -e

# Set login directory to root vagrant share
echo "cd /vagrant" > /etc/profile.d/login-directory.sh

# Configure Postgres
sudo -u postgres psql -U postgres -qf /vagrant/scripts/create_db.sql
sudo -u postgres psql -U postgres -qf /vagrant/scripts/create_test_db.sql

cd /vagrant

# Warn if Windows newlines are detected and try to fix the problem
if grep --quiet --binary --binary-files=without-match $(printf '\r') README.md; then
    echo
    cat scripts/crlf-warning.txt
    echo

    echo 'Running "git config core.autocrlf false"'
    git config core.autocrlf false

    exit 1
fi

# Set up the environment, the database, and run Gittip
cd /vagrant && make clean env schema data

# Output helper text
cat <<EOF

Gittip installed! To run,
$ vagrant ssh --command "make run"
EOF
