#!/bin/sh

set -e # exit when any command fails

pkgmissing() {
    if dpkg -l | grep 'ii  '$1' ' > /dev/null;
    then
        return 1;
    fi;
    return 0;
}

if pkgmissing postgresql-9.3; then
    if ! dpkg -l postgresql-9.3
    then
        echo " configuring apt for postgres-9.3"
        codename=`lsb_release -cs`
        aptlist="deb http://apt.postgresql.org/pub/repos/apt/ $codename-pgdg main"
        echo $aptlist | sudo tee /etc/apt/sources.list.d/pgdg.list > /dev/null
        wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -

        sudo apt-get update
    fi
    sudo apt-get install -y postgresql-9.3 postgresql-contrib
    sudo service postgresql start
fi;

if [ -z ""`psql template1 -tAc "select usename from pg_user where usename='$USER'"` ];
then
    sudo -u postgres createuser --superuser $USER
fi;

db_exists() {
    if [ -n ""`psql template1 -tAc "select datname from pg_database where datname='$1'"` ];
    then
        return 0;
    fi
    return 1;
}

if ! db_exists gittip-test;
then
    createdb gittip-test
    psql -q gittip-test -c 'alter database "gittip-test" set synchronous_commit to off'
fi

if ! db_exists gittip;
then
    createdb gittip
fi

dependencies="git make libpq-dev python-dev g++ language-pack-en"

for package in $dependencies; do
    if pkgmissing $package; then
        echo "missing:" $package
        pkgtoinstall=$pkgtoinstall" "$package
    fi
done

if [ -n "$pkgtoinstall" ]; then
    sudo apt-get install -y $pkgtoinstall;
fi;

echo "done"
