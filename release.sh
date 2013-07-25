#!/bin/sh

# Fail on error.
# ==============

set -e


# Be somewhere predictable.
# =========================

cd "`dirname $0`"


# --help
# ======

if [ $# = 0 ]; then
    echo
    echo "Usage: $0 <version>"
    echo
    echo "  This is a release script for Gittip. We bump the version number in "
    echo "  gittip/__init__.py and then do a git dance, pushing to Heroku."
    echo
    exit
fi


# Helpers
# =======

confirm () {
    proceed=""
    while [ "$proceed" != "y" ]; do
        read -p"$1 (y/N) " proceed
        if [ "$proceed" == "n" -o "$proceed" == "N" -o "$proceed" == "" ]
        then
            return 1
        fi
    done
    return 0
}

require () {
    if [ ! `which $1` ]; then
        echo "The '$1' command was not found."
        return 1 
    fi
    return 0
}


# Work
# ====

if [ $1 ]; then

    require git
    if [ $? -eq 1 ]; then
        exit 
    fi

    if [ "`git tag | grep $1`" ]; then
        echo "Version $1 is already git tagged."
    else
        confirm "Tag and push version $1?"
        if [ $? -eq 0 ]; then

            # Bump the version.
            # =================

            printf "$1\n" > www/version.txt
            git commit www/version.txt -m"Bump version to $1"
            git tag $1


            # Deploy to Heroku.
            # =================
            # If this fails we still want to bump the version again, so modify 
            # bash error handling around this call.

            set +e
            git push heroku master
            set -e


            # Bump the version again.
            # =======================
            # We're using a Pythonic convention here by using -dev to mean, "a
            # dev version following $whatever." We escape the dash for bash's
            # sake

            printf "$1\055dev\n" > www/version.txt
            git commit www/version.txt -m"Bump version to $1-dev"


            # Push to GitHub.
            # ===============
            # This will break if we didn't pull before releasing. We should do 
            # that.

            git push
            git push --tags

        fi
    fi
fi
