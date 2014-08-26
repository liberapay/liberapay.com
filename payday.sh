#!/bin/bash

# Fail on error.
# ==============

set -e


# Be somewhere predictable.
# =========================

cd "`dirname $0`"


# --help
# ======

if [ $# = 0 -o "$1" = "" ]; then
    echo
    echo "Usage: $0 <number> [\"for_real_please\"]"
    echo
    echo "  This is a payday wrapper script for Gratipay. It runs payday, logging to a file."
    echo "  You must pass at least one argument, a small integer indicating which week of "
    echo "  Gratipay you are running (it's only used to decide where to log). If you pass a"
    echo "  second arg then it must be the string \"for_real_please\", and in that case we"
    echo "  try to run against the production database. Without that string we run using "
    echo "  your local.env configuration."
    echo
    echo "  Payday is designed such that you can rerun it if it fails. In particular, it "
    echo "  will append to the log (not overwrite it)."
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

start () {
    echo "Logging to $LOG."
    echo >> $LOG
    date -u >> $LOG
}


# Work
# ====

if [ "$2" == "for_real_please" ]; then
    LOG="../paydays/gratipay-$1.log"
else
    LOG="../paydays/test-$1.log"
fi

if [ -f $LOG ]; then
    RUN="Rerun"
else
    # If the path is bad the next line will fail and we'll exit.
    touch $LOG
    RUN="Run"
fi

export PATH="./env/bin:$PATH"
require honcho
confirm "$RUN payday #$1?" || exit 0
case "$2" in
    "")
        start
        honcho run -e defaults.env,local.env payday >>$LOG 2>&1 &
        ;;
    "for_real_please")
        confirm "$RUN payday #$1 FOR REAL?!?!?!??!?!?" || exit 0
        start
        heroku config -s | honcho run -e /dev/stdin payday >>$LOG 2>&1 &
        ;;
    *)
        echo "Your second arg was $2. Wazzat mean?"
        exit 1
        ;;
esac

disown -a
tail -f $LOG
