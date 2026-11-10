#!/bin/bash
# release_dip.sh dipNN "message": commit pending changes, tag the build, push branch + tags to origin.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
tag=${1:?usage: release_dip.sh dipNN "message"}; msg=${2:-"$tag engine build"}
git rev-parse -q --verify "refs/tags/$tag" >/dev/null && { echo "tag $tag already exists"; exit 1; }
git add -A
git diff --cached --quiet || git commit -m "$tag: $msg"
git tag -a "$tag" -m "$tag: $msg"
git push origin HEAD --follow-tags
git push origin --tags
echo "released $tag at $(git rev-parse --short HEAD)"
