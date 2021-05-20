#!/bin/bash -eu

sudo -u webapp -E PYTHONPATH=. /var/app/venv/staging-*/bin/python liberapay/wireup.py
