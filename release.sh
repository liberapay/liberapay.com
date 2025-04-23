#!/bin/bash

# Fail on errors and undefined variables
set -eu

# Be somewhere predictable
cd "$(dirname "$0")"

# Constants
export APPNAME="${APPNAME-liberapay}"

# Helpers

yesno () {
    proceed=""
    while [ "$proceed" != "y" ]; do
        read -p"$1 (y/n) " proceed
        [ "$proceed" = "n" ] && return 1
    done
    return 0
}

read_after () {
    while read -r; do [ "$REPLY" = "$1" ] && break; done; cat
}

read_until () {
    while read -r; do [ "$REPLY" = "$1" ] && break || printf '%s\n' "$REPLY"; done
}

require () {
    if [ ! "$(which "$1")" ]; then
        echo "The '$1' command was not found."
        exit 1
    fi
}

# Check that we have the required tools
require eb
require git

# Check that we have the required credentials
sentry_token="$(cat .sentry-token 2>/dev/null || true)"
if [ -z "$sentry_token" ]; then
    echo "The Sentry API token is missing, please put it in the '.sentry-token' file (in the same directory as this script)."
    exit 1
fi

# Make sure we have the latest master
git checkout -q master
git pull

# Sync the translations
if yesno "Shall we sync translations first?"; then
    make i18n_update
fi

# Compute the next version number
prev="$(git describe --tags --match '[0-9]*' | cut -d- -f1)"
version="$((prev + 1))"

# Check for a branch.sql
branch_after=sql/branch-after.sql
branch_before=sql/branch-before.sql
if [ -e sql/branch.sql ]; then
    if [ "$(git show :sql/branch.sql)" != "$(<sql/branch.sql)" ]; then
        echo "sql/branch.sql has been modified" && exit 1
    fi

    schema_version_re="('schema_version',) +'([0-9]+)'"
    schema_version=$(sed -n -r -e "s/.*$schema_version_re.*/\2/p" sql/schema.sql)
    new_version=$((schema_version + 1))

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
    echo "$(<$branch_c)" | head --lines=-1 >>$out

    # Merge branch.sql into schema.sql
    sed -i -r -e "s/$schema_version_re/\1 '$new_version'/" sql/schema.sql
    echo -e '\n' | cat - sql/branch.sql >>sql/schema.sql

    # Let the user do the rest
    git rm sql/branch.sql
    echo "sql/branch.sql has been merged into sql/schema.sql and sql/migrations.sql"
    read -p "Please make the necessary manual modifications to those files now, then press Enter to continue... " enter

    # Check modifications to schema.sql
    echo "Testing sql/schema.sql..."
    while ! make test-schema; do
        read -p "Please fix sql/schema.sql, then press Enter to continue... " enter
        echo "Retesting sql/schema.sql..."
    done
    echo "Done. sql/schema.sql seems to be okay."

    # Commit changes
    git commit -m "merge branch.sql" -- sql/

    # Deployment stages
    echo "Splitting $branch_c in two..."
    cat "$branch_c" | read_until "SELECT 'after deployment';" > "$branch_before"
    cat "$branch_c" | read_after "SELECT 'after deployment';" > "$branch_after"
    if [ -s "$branch_before" ] || [ -s "$branch_after" ]; then
        echo "Done. Here is the result:" ; echo
        if [ -s "$branch_before" ]; then
            echo "--> $branch_before contains:" ; cat "$branch_before" ; echo
        else
            echo "--> $branch_before is empty"
        fi
        if [ -s "$branch_after" ]; then
            echo "--> $branch_after contains:" ; cat "$branch_after" ; echo
        else
            echo "--> $branch_after is empty" ; echo
        fi
    else
        echo "failure! $branch_before and $branch_after are both empty!"
        exit 1
    fi

    # Backup
    if yesno "Take a DB backup?"; then ./backup.sh; fi

    rm $branch_c
fi
run_schema_diff="$(test -s $branch_before -o -s $branch_after && echo "yes" || true)"

# Ask confirmation and bump the version
yesno "Tag and deploy version $version?" || exit
git tag $version -m ''

# Deploy
if [ -s $branch_before ]; then
    echo "Running $branch_before..."
    eb ssh liberapay -c 'psql -v ON_ERROR_STOP=on' <$branch_before
fi
[ -e $branch_before ] && rm $branch_before
eb deploy liberapay --label $version
if [ -s $branch_after ]; then
    echo "Running $branch_after..."
    eb ssh liberapay -c 'psql -v ON_ERROR_STOP=on' <$branch_after
fi
[ -e $branch_after ] && rm $branch_after

# Check for schema drift
if [ "$run_schema_diff" = 'yes' ]; then
#     echo "Checking for schema drift..."
#     if ! make schema-diff; then
#         echo "schema.sql doesn't match the production DB, please fix it"
#         exit 1
#     fi
    echo "Skipping broken schema drift check."
fi

# Push to GitHub
git push
git push --tags

# Tell Sentry about this release
curl https://sentry.io/api/0/organizations/liberapay/releases/ \
   -X POST \
   -H "Authorization: Bearer $sentry_token" \
   -H "Content-Type: application/json" \
   -d '{
         "version": "'$version'",
         "refs": [{
             "repository": "liberapay/liberapay.com",
             "commit": "'$(git rev-list -n 1 $version)'"
         }],
         "projects": ["liberapaycom"]
     }'
