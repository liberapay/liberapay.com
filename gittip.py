#!/usr/bin/env python

# OTHER CHANGES
# - Ignoring locale.Error in gittip/__init__.py
# - Remove psycopg2 from requirements.txt

import os
from fabricate import *


sources = ['program', 'util']


def run_lines(commands):
    for c in commands.split('\n', ):
        if not c.strip():
            continue
        print '$', c.strip()
        os.system(c.strip())
        print


def build():
    if not shell('python', '--version').startswith('Python 2.7'):
        raise SystemExit('Error: Python 2.7 required')

    c = """\
        python ./vendor/virtualenv-1.7.1.2.py \
        --with-site-packages \
        --unzip-setuptools \
        --prompt="[gittip] " \
        --never-download \
        --extra-search-dir=./vendor/ \
        --distribute \
        ./env/
    """.replace('\n', '') + """
        ./env/Scripts/pip install -r requirements.txt
        ./env/Scripts/pip install ./vendor/nose-1.1.2.tar.gz
        ./env/Scripts/pip install -e ./
        """

    run_lines(c.replace('/', os.sep))


def serve():
    #build()     #run: env local.env
    
    c = """\
    ./env/Scripts/swaddle local.env ./env/Scripts/aspen.exe \
    --www_root=www/ \
    --project_root=.. \
    --show_tracebacks=yes \
    --changes_reload=yes \
    --network_address=:8537""".replace('\n', '')

    run_lines(c.replace('/', os.sep))


"""
clean:
    rm -rf env *.egg *.egg-info tests/env
    find . -name \*.pyc -delete

local.env:
    echo "Creating a local.env file ..."
    echo
    echo "CANONICAL_HOST=" > local.env
    echo "CANONICAL_SCHEME=http" >> local.env
    echo "DATABASE_URL=postgres://gittip@localhost/gittip" >> local.env
    echo "STRIPE_SECRET_API_KEY=1" >> local.env
    echo "STRIPE_PUBLISHABLE_API_KEY=1" >> local.env
    echo "BALANCED_API_SECRET=90bb3648ca0a11e1a977026ba7e239a9" >> local.env
    echo "GITHUB_CLIENT_ID=3785a9ac30df99feeef5" >> local.env
    echo "GITHUB_CLIENT_SECRET=e69825fafa163a0b0b6d2424c107a49333d46985" >> local.env
    echo "GITHUB_CALLBACK=http://localhost:8537/on/github/associate" >> local.env
    echo "TWITTER_CONSUMER_KEY=QBB9vEhxO4DFiieRF68zTA" >> local.env
    echo "TWITTER_CONSUMER_SECRET=mUymh1hVMiQdMQbduQFYRi79EYYVeOZGrhj27H59H78" >> local.env
    echo "TWITTER_CALLBACK=http://127.0.0.1:8537/on/twitter/associate" >> local.env

run: env local.env
    ./env/Scripts/swaddle local.env ./env/Scripts/aspen \
        --www_root=www/ \
        --project_root=.. \
        --show_tracebacks=yes \
        --changes_reload=yes \
        --network_address=:8537

test: env tests/env data
    ./env/Scripts/swaddle tests/env ./env/Scripts/nosetests ./tests/

tests: test

tests/env:
    echo "Creating a tests/env file ..."
    echo
    echo "CANONICAL_HOST=" > tests/env
    echo "CANONICAL_SCHEME=http" >> tests/env
    echo "DATABASE_URL=postgres://gittip-test@localhost/gittip-test" >> tests/env
    echo "STRIPE_SECRET_API_KEY=1" >> tests/env
    echo "STRIPE_PUBLISHABLE_API_KEY=1" >> tests/env
    echo "BALANCED_API_SECRET=90bb3648ca0a11e1a977026ba7e239a9" >> tests/env
    echo "GITHUB_CLIENT_ID=3785a9ac30df99feeef5" >> tests/env
    echo "GITHUB_CLIENT_SECRET=e69825fafa163a0b0b6d2424c107a49333d46985" >> tests/env
    echo "GITHUB_CALLBACK=http://localhost:8537/on/github/associate" >> tests/env
    echo "TWITTER_CONSUMER_KEY=QBB9vEhxO4DFiieRF68zTA" >> tests/env
    echo "TWITTER_CONSUMER_SECRET=mUymh1hVMiQdMQbduQFYRi79EYYVeOZGrhj27H59H78" >> tests/env
    echo "TWITTER_CALLBACK=http://127.0.0.1:8537/on/twitter/associate" >> tests/env

data: env
    ./makedb.sh gittip-test gittip-test
    ./env/Scripts/swaddle tests/env ./env/Scripts/python ./gittip/testing.py
"""


def clean():
    autoclean()


main()
