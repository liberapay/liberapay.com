#!/bin/bash

# Tell bash to be strict and log everything
set -eux

# Compute the deployment ID
deploy_id=$(($(cat /var/app/_deploy_id 2>/dev/null || echo 0) + 1))
max_deploy_id=$((deploy_id + 99))
while systemctl is-active --quiet webapp@$deploy_id.service; do
    let deploy_id++
    if [ $deploy_id -gt $max_deploy_id ]; then
        echo "this script appears to be stuck in an infinite loop, exiting"
        exit 1
    fi
done

# Rename the app directory
app_dir=$(pwd)
rm -rf /var/app/$deploy_id
mv $app_dir /var/app/$deploy_id
ln -s /var/app/$deploy_id $app_dir

# Start the new instance and its proxy
systemctl start webapp@$deploy_id.service cloudflared@$deploy_id.service

# Save the new deployment ID
echo $deploy_id >/var/app/_deploy_id

# Stop the old instance(s) and their proxies
let i=1
while [ $i -lt $deploy_id ]; do
    systemctl stop cloudflared@$i.service
    systemctl stop webapp@$i.service
    systemctl stop webapp@$i.socket
    rm -rf /var/app/$i
    let i++
done
