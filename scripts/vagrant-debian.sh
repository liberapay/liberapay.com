#!/usr/bin/env bash

# installs Python-independent project dependencies

apt-get -y install postgresql
apt-get -y install libpq-dev
apt-get -y install python-dev  # for building psycopg2
apt-get -y install g++  # for libsass
apt-get -y install git  # release.sh and commit process
apt-get -y install npm  # for jstests
