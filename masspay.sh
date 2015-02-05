#!/bin/sh
heroku config -s | honcho run -e /dev/stdin ./env/bin/python ./bin/masspay.py -i
./bin/masspay.py -o
