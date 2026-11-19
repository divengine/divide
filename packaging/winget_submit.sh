#!/usr/bin/env bash
# A version's winget manifests, as a pull request to microsoft/winget-pkgs.
#
#   GH_TOKEN=... packaging/winget_submit.sh 0.2.0 DIR [--dry-run]
#
# DIR holds manifests/d/Divengine/Divide/<version>/ (packaging/manifests.py --winget DIR).
# The token is a classic one with public_repo: the pull request comes from its user's fork of
# winget-pkgs (made if missing, brought up to date first). Only the package's folder is checked
# out: winget-pkgs is large. --dry-run stops before pushing.
set -euo pipefail

version=$1
dir=$(cd "$2" && pwd)
dry=${3:-}
upstream=microsoft/winget-pkgs
folder=manifests/d/Divengine/Divide
[ -d "$dir/$folder/$version" ] || { echo "no manifests in $dir/$folder/$version" >&2; exit 1; }

login=$(gh api user --jq .login)
if ! gh api "repos/$login/winget-pkgs" --silent 2>/dev/null; then
  gh repo fork "$upstream" --clone=false
  for _ in $(seq 30); do gh api "repos/$login/winget-pkgs" --silent 2>/dev/null && break; sleep 5; done
fi
gh repo sync "$login/winget-pkgs" --source "$upstream" --branch master

new=true
if gh api "repos/$upstream/contents/$folder" --silent 2>/dev/null; then
  new=false
fi
if gh api "repos/$upstream/contents/$folder/$version" --silent 2>/dev/null; then
  echo "winget-pkgs already has Divengine.Divide $version."
  exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone --quiet --depth 1 --filter=blob:none --no-checkout \
  "https://x-access-token:${GH_TOKEN}@github.com/$login/winget-pkgs.git" "$work/pkgs"
cd "$work/pkgs"
git sparse-checkout set --no-cone "/$folder/"
git checkout --quiet master
branch="Divengine.Divide-$version"
git switch --quiet -c "$branch"
mkdir -p "$folder"
cp -r "$dir/$folder/$version" "$folder/"
git add "$folder/$version"
title=$([ "$new" = true ] && echo "New package: Divengine.Divide version $version" \
                          || echo "New version: Divengine.Divide version $version")
git -c user.name="divide release" -c user.email="divide-release@users.noreply.github.com" \
  commit --quiet -m "$title"
git show --stat --format=%s HEAD
if [ "$dry" = --dry-run ]; then
  echo "dry run: not pushed"
  exit 0
fi
git push --quiet --force origin "$branch"
gh pr create --repo "$upstream" --base master --head "$login:$branch" --title "$title" \
  --body "divide $version: https://github.com/divengine/divide/releases/tag/v$version"
