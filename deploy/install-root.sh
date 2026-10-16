#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Root console required'; exit 1; }
[ "$(hostname)" = srv1372645 ] || { echo 'Unexpected VPS'; exit 1; }
base=/home/pete-dev/flux-studio
[ -f "$base/.env" ]
[ -f /home/pete-dev/projects/pete-mcp-gateway/.secrets/browser_passcode.json ]
install -d -m 0700 /opt/flux-studio-public
install -m 0600 "$base/.env" /opt/flux-studio-public/runtime.env
install -m 0644 "$base/deploy/compose-public.yml" /opt/flux-studio-public/compose.yml
install -m 0755 "$base/deploy/flux-studio-admin" /usr/local/sbin/flux-studio-admin
printf '%s\n' 'pete-dev ALL=(root) NOPASSWD: /usr/local/sbin/flux-studio-admin status, /usr/local/sbin/flux-studio-admin update, /usr/local/sbin/flux-studio-admin restart' > /root/flux-studio-sudoers.prepared
visudo -cf /root/flux-studio-sudoers.prepared
install -m 0440 /root/flux-studio-sudoers.prepared /etc/sudoers.d/flux-studio
printf '%s\n' 'Limited Studio deployment helper installed. General sudo unchanged.'
