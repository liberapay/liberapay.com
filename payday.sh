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
    echo "Usage: $0 <number> [\"for_real_please\"]"
    echo
    echo "  This is a payday wrapper script for Gittip. It runs payday, logging to a file."
    echo "  You must pass at least one argument, a small integer indicating which week of "
    echo "  Gittip you are running (it's only used to decide where to log). If you pass a"
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
    LOG="../paydays/gittip-$1.log"
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

if [ $1 ]; then
    require foreman
    confirm "$RUN payday #$1?"
    if [ $? -eq 0 ]; then
        if [ "$2" == "" ]; then
            start
            foreman run -e local.env ./env/bin/payday >> $LOG 2>&1
        else 
            if [ "$2" == "for_real_please" ]; then
                confirm "$RUN payday #$1 FOR REAL?!?!?!??!?!?"
                if [ $? -eq 0 ]; then
                    start
                    heroku config -s | foreman run -e /dev/stdin \
                        ./env/bin/payday >> $LOG 2>&1
                fi
            else
                echo "Your second arg was $2. Wazzat mean?"
            fi
        fi
    fi
fi
