#!/usr/bin/env bash

set -e

# Set login directory to root vagrant share
sudo sh -c "echo 'cd /vagrant' > /etc/profile.d/login-directory.sh"

# Configure Postgres (using system user 'postgres' run command
# 'psql' with PostreSQL user 'postgres` to quietly execute scripts)
sudo -u postgres psql -U postgres -qf /vagrant/scripts/create_db.sql
sudo -u postgres psql -U postgres -qf /vagrant/scripts/create_test_db.sql

# Set up the environment, the database, and run Gratipay
cd /vagrant && make clean env schema data

# Output helper text
cat <<EOF

Gratipay installed! To run,
$ vagrant ssh --command "make run"
EOF
