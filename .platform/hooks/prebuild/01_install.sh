#!/bin/bash

# Tell bash to be strict and log everything
set -eux

# Install libffi-devel for misaka, and htop for when I want to look at what's going on
yum install -y libffi-devel htop
# Install PostgreSQL client tools and libraries
amazon-linux-extras install -y postgresql11

# Automatically set the PG* environment variables so that `psql` connects to the liberapay database by default
install -m 644 -o root -g root -t /etc/profile.d .platform/files/pgenv.sh

# Install the systemd service files for the webapp and cloudflared
install -m 644 -o root -g root -t /etc/systemd/system .platform/files/cloudflared@.service
install -m 644 -o root -g root -t /etc/systemd/system .platform/files/webapp@.service
install -m 644 -o root -g root -t /etc/systemd/system .platform/files/webapp@.socket
systemctl daemon-reload

# Install cloudflared, directly from GitHub
if ! which cloudflared 2>/dev/null || [ $(cloudflared version) != "cloudflared version 2021.5.8 "* ]; then
    wget https://github.com/cloudflare/cloudflared/releases/download/2021.5.8/cloudflared-linux-amd64
    hash=$(sha256sum cloudflared-linux-amd64 | cut -d' ' -f1)
    expected_hash=224cd850cb042a5da1d15432063ed04bf8764241de769338e65c44639ed6c28e
    if [ $hash != $expected_hash ]; then
        echo "cloudflared binary downloaded from GitHub doesn't match expected hash: $hash != $expected_hash"
        exit 1
    fi
    install -m 755 -o root -g root cloudflared-linux-amd64 /usr/local/bin/cloudflared
    rm cloudflared-linux-amd64
fi

# Create the cloudflared system user and group
groupadd -r cloudflared || true
useradd -r -g cloudflared cloudflared || true

# Install the Cloudflare Tunnel configuration and credentials files
install -o cloudflared -g cloudflared -m 755 -d /etc/cloudflared
install -o cloudflared -g cloudflared -m 644 -t /etc/cloudflared .platform/files/cloudflared.conf
if ! [ -f /etc/cloudflared/liberapay-prod.json ]; then
    aws s3 cp s3://serverfiles.liberapay.org/liberapay-prod.json liberapay-prod.json
    install -o cloudflared -g cloudflared -m 644 -t /etc/cloudflared liberapay-prod.json
    rm liberapay-prod.json
fi
