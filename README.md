# Codex Config

Personal Codex instructions and skills for frontend design, repository cleanup, Python dead-code removal, behavior-preserving code pruning, PR merging, rephrasing, and summarizing.

## Installation and syncing

This repository is checked out directly at `~/.codex`. Skills under `skills/` are therefore already in the user skills directory; no symlinks or copy step are needed. On another machine with the same setup, run `git -C ~/.codex pull --ff-only` to receive committed and pushed updates.

## Frontend design skill

[`skills/frontend-design/`](skills/frontend-design/) is an unmodified copy of Anthropic's [frontend-design skill](https://github.com/anthropics/skills/tree/main/skills/frontend-design) from the [`anthropics/skills`](https://github.com/anthropics/skills) repository.

- Copied upstream commit: [`2c5958ecac7cee2b583967a2c4981d0f4a75c579`](https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/frontend-design).
- License: Apache 2.0, preserved in [`skills/frontend-design/LICENSE.txt`](skills/frontend-design/LICENSE.txt).
- Only this skill's folder is included, as ordinary tracked files.

### Updating from upstream

Start with a clean working tree. Run these commands in a shell with Git and rsync installed. They download upstream into a temporary directory and replace only the copied skill folder, including removal of files deleted upstream:

```sh
cd ~/.codex
upstream_dir=$(mktemp -d)
git clone --depth 1 --filter=blob:none --sparse https://github.com/anthropics/skills.git "$upstream_dir" &&
  git -C "$upstream_dir" sparse-checkout set skills/frontend-design &&
  rsync -a --delete "$upstream_dir/skills/frontend-design/" skills/frontend-design/ &&
  git -C "$upstream_dir" rev-parse HEAD
```

If the commands succeed, replace the copied upstream commit and its link above with the printed SHA. Preserve the upstream license and supporting files. Review `git diff` and `git status --short`, then commit and push the skill files and README together. You can then remove the temporary directory with `rm -rf "$upstream_dir"`.

Other machines checked out at `~/.codex` receive the updated skill with a normal `git pull --ff-only`.
