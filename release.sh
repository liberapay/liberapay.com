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
    echo "  www/version.txt and then do a git dance, pushing to Heroku."
    echo
    exit
fi


# Helpers
# =======

confirm () {
    proceed=""
    while [ "$proceed" != "y" ]; do
        read -p"$1 (y/N) " proceed
        if [ "$proceed" = "n" -o "$proceed" = "N" -o "$proceed" = "" ]
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

    if [ "`git rev-parse --abbrev-ref HEAD`" != "master" ]; then
        echo "Not on master, checkout master first."
        exit
    fi

    # Make sure we have the latest master.
    # ====================================

    git pull

    if [ "`git tag | grep $1`" ]; then
        echo "Version $1 is already git tagged."
        exit
    fi

    if ! grep -e \-dev$ www/version.txt > /dev/null; then
        echo "Current version does not end with '-dev'."
        exit
    fi

    confirm "Tag and push version $1?"
    if [ $? -eq 0 ]; then

        # Bump the version.
        # =================

        printf "$1\n" > www/version.txt
        git commit www/version.txt -m"Bump version to $1"
        git tag $1


        # Deploy to Heroku.
        # =================

        git push heroku master


        # Bump the version again.
        # =======================
        # We're using a Pythonic convention here by using -dev to mean, "a
        # dev version following $whatever." We escape the dash for bash's
        # sake

        printf "$1\055dev\n" > www/version.txt
        git commit www/version.txt -m"Bump version to $1-dev"


        # Push to GitHub.
        # ===============

        git push
        git push --tags

    fi
fi
