#!/usr/bin/env bash
set -Eeuo pipefail

# Run as ubuntu: bash deploy.sh /home/ubuntu/incoming/RELEASE RELEASE
source_dir="${1:?Usage: deploy.sh SOURCE_DIR RELEASE_ID}"
release_id="${2:?Release ID required}"
[[ "$release_id" =~ ^[a-f0-9]{40}-[0-9]+-[0-9]+$ ]] || { echo 'Invalid release ID' >&2; exit 1; }
source_dir="$(realpath "$source_dir")"
[[ -s "$source_dir/build/index.html" ]]
[[ "$(cat "$source_dir/build/version.txt")" == "$release_id" ]]
[[ -f "$source_dir/deployment/ref-card.service" ]]
[[ -f "$source_dir/deployment/nginx.conf" ]]

base=/opt/ref-card
sudo install -d -m 755 "$base/releases"
exec 9>/home/ubuntu/.m324-deploy.lock
flock -w 120 9
release="$base/releases/$release_id"
if sudo test -e "$release"; then
    echo 'Release already exists; rerun the workflow to get a new attempt ID.' >&2
    exit 1
fi
previous="$(readlink -f "$base/current" || true)"
sudo mkdir "$release"
sudo cp -R "$source_dir/build" "$source_dir/deployment" "$release/"
sudo chown -R root:root "$release"
sudo chmod -R u=rwX,go=rX "$release"
# Validate syntax before changing the running release.
sudo nginx -t -c "$release/deployment/nginx.conf"

rollback() {
    trap - ERR
    echo 'Deployment failed; restoring previous release.' >&2
    if [[ -n "$previous" && -d "$previous" ]]; then
        sudo ln -sfn "$previous" "$base/current.next"
        sudo mv -Tf "$base/current.next" "$base/current"
        sudo install -m 644 "$previous/deployment/ref-card.service" /etc/systemd/system/ref-card.service
        sudo systemctl daemon-reload
        sudo systemctl restart ref-card.service
    else
        sudo systemctl disable --now ref-card.service || true
        sudo rm -f "$base/current"
    fi
    exit 1
}
trap rollback ERR
sudo ln -sfn "$release" "$base/current.next"
sudo mv -Tf "$base/current.next" "$base/current"
sudo install -m 644 "$release/deployment/ref-card.service" /etc/systemd/system/ref-card.service
sudo systemctl daemon-reload
sudo systemctl enable ref-card.service
sudo systemctl restart ref-card.service

healthy=false
for attempt in {1..15}; do
    if sudo systemctl is-active --quiet ref-card.service &&
       [[ "$(curl --fail --silent --max-time 3 http://127.0.0.1:8080/version.txt || true)" == "$release_id" ]] &&
       curl --fail --silent --max-time 3 http://127.0.0.1:8080/ >/dev/null; then
        healthy=true
        break
    fi
    sleep 2
done
[[ "$healthy" == true ]]
trap - ERR
echo "Deployed $release_id on port 8080"
