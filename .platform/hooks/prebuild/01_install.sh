#!/bin/bash

# Tell bash to be strict and log everything
set -eux

# Install libffi-devel for misaka, and htop for when I want to look at what's going on
dnf install -y libffi-devel htop
# Install PostgreSQL client tools and libraries
dnf install -y postgresql15

# Automatically set the PG* environment variables so that `psql` connects to the liberapay database by default
install -m 644 -o root -g root -t /etc/profile.d .platform/files/pgenv.sh

# Install the systemd service files for the webapp and cloudflared
install -m 644 -o root -g root -t /etc/systemd/system .platform/files/cloudflared@.service
install -m 644 -o root -g root -t /etc/systemd/system .platform/files/webapp@.service
install -m 644 -o root -g root -t /etc/systemd/system .platform/files/webapp@.socket
systemctl daemon-reload

# Install cloudflared, directly from GitHub
target_cfd_version="2026.10.7"
function get_installed_cfd_version() {
    if [ -x /usr/local/bin/cloudflared ]; then
        /usr/local/bin/cloudflared version | \
        sed -E -e 's/^cloudflared version ([^ ]+).*/\1/'
    fi
}
installed_cfd_version="$(get_installed_cfd_version)"
if [ "$installed_cfd_version" != "$target_cfd_version" ]; then
    if [ "$installed_cfd_version" = "" ]; then
        echo "Installing cloudflared (version $target_cfd_version)"
    else
        echo "Upgrading cloudflared ($installed_cfd_version -> $target_cfd_version)"
    fi
    wget "https://github.com/cloudflare/cloudflared/releases/download/$target_cfd_version/cloudflared-linux-amd64"
    hash=$(sha256sum cloudflared-linux-amd64 | cut -d' ' -f1)
    expected_hash=1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872
    if [ $hash != $expected_hash ]; then
        echo "cloudflared binary downloaded from GitHub doesn't match expected hash: $hash != $expected_hash"
        exit 1
    fi
    install -m 755 -o root -g root cloudflared-linux-amd64 /usr/local/bin/cloudflared
    rm cloudflared-linux-amd64
    if [ "$(get_installed_cfd_version)" = "$installed_cfd_version" ]; then
        echo "upgrading cloudflared failed"
        exit 1
    fi
else
    echo "cloudflared version $target_cfd_version is already installed"
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
