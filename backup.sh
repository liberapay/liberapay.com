#!/usr/bin/env bash

# Fail on error.
# ==============

set -e


# Be somewhere predictable.
# =========================

cd "`dirname $0`"


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

get_filepath () {
    TODAY="`date +%F`"
    CANDIDATE="$DIRPATH/$TODAY.psql"
    if [ -f "$CANDIDATE" ]
    then
        echo "      $CANDIDATE" >&2
        for x in {a..z}
        do
            CANDIDATE="$DIRPATH/$TODAY$x.psql"
            if [ ! -f "$CANDIDATE" ]
            then
                break
            fi
            echo "      $CANDIDATE" >&2
        done
        if [ -f "$CANDIDATE" ]
        then
            CANDIDATE=""
        else
            echo "----> $CANDIDATE" >&2
            echo >&2
        fi
    fi
    echo "$CANDIDATE"
}


# Work
# ====

require foreman
require heroku
require pg_dump

DIRPATH="../backups"
FILEPATH=$(get_filepath)

if [ "$FILEPATH" = "" ]
then
    exit "Too many backups!"
fi

confirm "Backup the Gittip database to $FILEPATH?"
if [ $? -eq 0 ]; then
    export PGSSLMODE=require
    heroku config -s -a gittip \
        | foreman run -e /dev/stdin ./configure-pg-env.sh \
        | foreman run -e /dev/stdin pg_dump > $FILEPATH
fi
