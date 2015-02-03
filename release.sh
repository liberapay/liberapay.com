#!/bin/sh


# Fail on error
set -e


# Be somewhere predictable
cd "`dirname $0`"


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
require heroku
require git


# Make sure we have the latest master
if [ "`git rev-parse --abbrev-ref HEAD`" != "master" ]; then
    echo "Not on master, checkout master first."
    exit
fi
git pull


# Compute the next version number
prev="$(git describe --tags --match '[0-9]*' | cut -d- -f1 | sed 's/\.//g')"
version="$((prev + 1))"


# Check that the environment contains all required variables
heroku config -sa gratipay | ./env/bin/honcho run -e /dev/stdin \
    ./env/bin/python gratipay/wireup.py


# Sync the translations
echo "Syncing translations..."
if [ ! -e .transifexrc -a ! -e ~/.transifexrc ]; then
    heroku config -sa gratipay | ./env/bin/honcho run -e /dev/stdin make transifexrc
fi
make i18n_upload
make i18n_download
git add i18n
if git commit --dry-run &>/dev/null; then git commit -m "update i18n files"; fi


# Check for a branch.sql
if [ -e branch.sql ]; then
    # Merge branch.sql into schema.sql
    git rm --cached branch.sql
    echo | cat branch.sql >>schema.sql
    echo "branch.sql has been appended to schema.sql"
    read -p "If you have manual modifications to make to schema.sql do them now, then press Enter to continue... " enter
    git add schema.sql
    git commit -m "merge branch.sql into schema.sql"

    # Deployment options
    if yesno "Should branch.sql be applied before deploying to Heroku instead of after?"; then
        run_sql="before"
        if yesno "Should the maintenance mode be turned on during deployment?"; then
            maintenance="yes"
        fi
    else
        run_sql="after"
    fi
fi


# Ask confirmation and bump the version
yesno "Tag and deploy version $version?" || exit
echo $version >www/version.txt
git commit www/version.txt -m "Bump version to $version"
git tag $version


# Deploy to Heroku
[ "$maintenance" = "yes" ] && heroku maintenance:on -a gratipay
[ "$run_sql" = "before" ] && heroku pg:psql -a gratipay <branch.sql
git push --force heroku master
[ "$maintenance" = "yes" ] && heroku maintenance:off -a gratipay
[ "$run_sql" = "after" ] && heroku pg:psql -a gratipay <branch.sql
rm -f branch.sql


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
