#!/bin/bash -eu

/var/app/venv/staging-*/bin/pip install --no-build-isolation --require-hashes -r requirements_setup.txt
/var/app/venv/staging-*/bin/pip install --no-build-isolation --require-hashes -r requirements_base.txt
