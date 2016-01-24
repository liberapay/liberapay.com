#!/bin/sh

# Fail on error
set -e

# Be somewhere predictable
cd "`dirname $0`"

# Constants
APPNAME=liberapay

# Helpers

yesno () {
    proceed=""
    while [ "$proceed" != "y" ]; do
        read -p"$1 (y/n) " proceed
        [ "$proceed" = "n" ] && return 1
    done
    return 0
}

require () {
    if [ ! `which $1` ]; then
        echo "The '$1' command was not found."
        exit 1
    fi
}

# Check that we have the required tools
require rhc
require git

# Make sure we have the latest master
git checkout -q master
git pull

# Compute the next version number
prev="$(git describe --tags --match '[0-9]*' | cut -d- -f1)"
version="$((prev + 1))"

# Check that the environment contains all required variables
rhc ssh $APPNAME env | ./env/bin/honcho run -e /dev/stdin \
    ./env/bin/python liberapay/wireup.py

# Sync the translations
echo "Syncing translations..."
make i18n_pull
make i18n_update

# Check for a branch.sql
if [ -e sql/branch.sql ]; then
    # Merge branch.sql into schema.sql
    git rm --cached sql/branch.sql
    echo | cat sql/branch.sql >>sql/schema.sql
    echo "sql/branch.sql has been appended to sql/schema.sql"
    read -p "Please make the necessary manual modifications to schema.sql now, then press Enter to continue... " enter
    git add sql/schema.sql
    git commit -m "merge branch.sql into schema.sql"

    # Deployment options
    if yesno "Should branch.sql be applied before deploying instead of after?"; then
        run_sql="before"
        if yesno "Should the app be stopped during deployment?"; then
            maintenance="yes"
        fi
    else
        run_sql="after"
    fi
fi

# Ask confirmation and bump the version
yesno "Tag and deploy version $version?" || exit
git tag $version

# Deploy
[ "$maintenance" = "yes" ] && rhc app stop $APPNAME
[ "$run_sql" = "before" ] && rhc ssh $APPNAME psql <sql/branch.sql
git push --force openshift master
[ "$maintenance" = "yes" ] && rhc app start $APPNAME
[ "$run_sql" = "after" ] && rhc ssh $APPNAME psql <sql/branch.sql
rm -f sql/branch.sql

# Push to GitHub
git push
git push --tags

# Check for schema drift
if [[ $run_sql ]]; then
    if ! make schema-diff; then
        echo "schema.sql doesn't match the production DB, please fix it"
        exit 1
    fi
fi
