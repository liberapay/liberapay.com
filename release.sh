#!/bin/sh

# Fail on errors and undefined variables
set -eu

# Be somewhere predictable
cd "`dirname $0`"

# Constants
export APPNAME=${APPNAME-liberapay}

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

# Sync the translations
if yesno "Shall we sync translations first?"; then
    make i18n_update
fi

# Check that we have the required tools
require rhc
require git

# Make sure we have the latest master
git checkout -q master
git pull

# Compute the next version number
prev="$(git describe --tags --match '[0-9]*' | cut -d- -f1)"
version="$((prev + 1))"

# Check the configuration
rhc ssh liberapay 'cd $OPENSHIFT_REPO_DIR; PYTHONPATH=. python liberapay/wireup.py'

# Check for a branch.sql
if [ -e sql/branch.sql ]; then
    if [ "$(git show :sql/branch.sql)" != "$(<sql/branch.sql)" ]; then
        echo "sql/branch.sql has been modifed" && exit 1
    fi

    schema_version_re="('schema_version',) +'([0-9]+)'"
    schema_version=$(sed -n -r -e "s/.*$schema_version_re.*/\2/p" sql/schema.sql)
    new_version=$(($schema_version + 1))

    # Run branch.sql on the test DB in echo mode to get back a "compiled"
    # version on stdout without commands like \i
    branch_c=sql/branch-compiled.sql
    echo "Compiling branch.sql into $branch_c..."
    cp sql/branch.sql $branch_c
    echo >>$branch_c
    echo "UPDATE db_meta SET value = '$new_version'::jsonb WHERE key = 'schema_version';" >>$branch_c
    $(make echo var=with_tests_env) sh -eu -c "
        psql \$DATABASE_URL -v ON_ERROR_STOP=on <sql/recreate-schema.sql >/dev/null
        psql -e \$DATABASE_URL -v ON_ERROR_STOP=on -o /dev/null <$branch_c >$branch_c.
    "
    mv $branch_c{.,}
    echo "Done."

    # Merge branch.sql into migrations.sql
    out=sql/migrations.sql
    echo -e '\n-- migration' "#$new_version" >>$out
    ./env/bin/python -c "print(open('sql/branch.sql').read().strip())" >>$out

    # Merge branch.sql into schema.sql
    sed -i -r -e "s/$schema_version_re/\1 '$new_version'/" sql/schema.sql
    echo -e '\n' | cat - sql/branch.sql >>sql/schema.sql

    # Let the user do the rest, then commit
    git rm sql/branch.sql
    echo "sql/branch.sql has been merged into sql/schema.sql and sql/migrations.sql"
    read -p "Please make the necessary manual modifications to those files now, then press Enter to continue... " enter
    git add sql/{schema,migrations}.sql
    git commit -m "merge branch.sql"

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
[ "${maintenance-}" = "yes" ] && rhc app stop $APPNAME
[ "${run_sql-}" = "before" ] && rhc ssh $APPNAME 'psql -v ON_ERROR_STOP=on' <$branch_c
git push --force openshift master
[ "${maintenance-}" = "yes" ] && rhc app start $APPNAME
[ "${run_sql-}" = "after" ] && rhc ssh $APPNAME 'psql -v ON_ERROR_STOP=on' <$branch_c
[ "${branch_c-}" != "" ] && rm -f $branch_c

# Push to GitHub
git push
git push --tags

# Check for schema drift
if [[ ${run_sql-} ]]; then
    if ! make schema-diff; then
        echo "schema.sql doesn't match the production DB, please fix it"
        exit 1
    fi
fi
