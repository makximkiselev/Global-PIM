#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "git_release_safety: not a git worktree"
  exit 0
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" == "HEAD" ]]; then
  echo "git_release_safety: detached HEAD"
  exit 1
fi

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>/dev/null || true)"
if [[ -z "$upstream" ]]; then
  echo "git_release_safety: branch $branch has no upstream"
  exit 1
fi

git fetch --quiet "${upstream%%/*}" || {
  echo "git_release_safety: fetch failed for $upstream"
  exit 1
}

read -r behind ahead < <(git rev-list --left-right --count "$upstream...HEAD")
dirty="$(git status --porcelain --untracked-files=no)"

echo "git_release_safety: branch=$branch upstream=$upstream ahead=$ahead behind=$behind"
if [[ -n "$dirty" ]]; then
  echo "git_release_safety: tracked working tree is dirty"
  git status --short --untracked-files=no
  exit 1
fi

if [[ "$behind" != "0" ]]; then
  echo "git_release_safety: local branch is behind upstream; rebase or merge before release"
  exit 1
fi

echo "git_release_safety: ok"
