#!/bin/sh


# Fail on error
set -e


# Be somewhere predictable
cd "`dirname $0`"


# --help
if [ "$1" = "" ]; then
    echo
    echo "Usage: $0 <version>"
    echo
    echo "  This is a release script for Gratipay. We do a git dance, pushing to Heroku."
    echo
    exit
fi


# Helpers

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

if [ "`git tag | grep $1`" ]; then
    echo "Version $1 is already git tagged."
    exit
fi


# Check that the environment contains all required variables
heroku config -sa gratipay | ./env/bin/honcho run -e /dev/stdin \
    ./env/bin/python gratipay/wireup.py


# Ask confirmation and bump the version
confirm "Tag and push version $1?" || exit
git tag $1


# Deploy to Heroku
git push heroku master


# Push to GitHub
git push
git push --tags
