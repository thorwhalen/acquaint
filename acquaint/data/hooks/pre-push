#!/bin/sh
# acquaint pre-push guard, installed by `acquaint sync init`.
#
# Refuses to push this profile store anywhere except the private GitHub repository it
# was set up for. Every one of these must hold, or nothing is pushed:
#   - the push goes through the remote named origin (not a URL, not another remote);
#   - origin has exactly one url, the one recorded at init, and no pushurl that differs;
#   - git is pushing to that url (no url.*.pushInsteadOf rewrite in between);
#   - that url is one of the forms that name the recorded github.com repository;
#   - `gh` reports that repository, on github.com, as PRIVATE right now.
# It fails closed: missing configuration, a missing `gh`, or any other answer means no push.
#
# A seatbelt, not a lock: `git push --no-verify` skips it, and whoever controls this
# repository's git config or the `gh` on PATH controls what it sees.

remote_name="$1"
push_url="$2"
repo=$(git config --get acquaint.repo)
expected=$(git config --get acquaint.remote)

refuse() {
  echo "acquaint: $1; refusing to push profile data." >&2
  exit 1
}

lower() {
  printf '%s' "$1" | tr 'A-Z' 'a-z'
}

[ -n "$repo" ] && [ -n "$expected" ] || refuse "no sync configuration (acquaint.repo, acquaint.remote)"
[ "$remote_name" = "origin" ] || refuse "pushes go through origin only, not '$remote_name'"
[ "$(git config --get-all remote.origin.url)" = "$expected" ] || refuse "origin must have exactly one url, '$expected'"
pushurls=$(git config --get-all remote.origin.pushurl)
[ -z "$pushurls" ] || [ "$pushurls" = "$expected" ] || refuse "origin has a pushurl other than '$expected'"
[ "$push_url" = "$(git remote get-url origin)" ] || refuse "git is pushing to '$push_url', not to origin's url (a url.*.pushInsteadOf rewrite?)"

named=""
for form in "git@github.com:$repo.git" "git@github.com:$repo" "ssh://git@github.com/$repo.git" "ssh://git@github.com/$repo" "https://github.com/$repo.git" "https://github.com/$repo"; do
  if [ "$(lower "$expected")" = "$(lower "$form")" ]; then
    named=yes
  fi
done
[ -n "$named" ] || refuse "'$expected' is not a url of the GitHub repository $repo"

visibility=$(GH_HOST=github.com gh repo view "$repo" --json visibility -q .visibility 2>/dev/null)
[ "$visibility" = "PRIVATE" ] || refuse "$repo is '${visibility:-unknown}', not PRIVATE"

exit 0
