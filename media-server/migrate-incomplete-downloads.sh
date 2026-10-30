#!/bin/sh

set -eu

state_dir=${1:?state volume path is required}
incomplete_dir=${2:?incomplete-download volume path is required}
migration_marker="$incomplete_dir/.legacy-state-migration-complete"

mkdir -p "$incomplete_dir/usenet" "$incomplete_dir/torrent"

if [ -e "$migration_marker" ]; then
    exit 0
fi

for category in usenet torrent; do
    source_dir="$state_dir/downloads/$category/incomplete"
    target_dir="$incomplete_dir/$category"

    if [ -d "$source_dir" ]; then
        cp -a "$source_dir"/. "$target_dir"/
        rm -rf "$source_dir"
    fi
done

touch "$migration_marker"
