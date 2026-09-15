# acquaint.sync

Private-repository sync for the data root: create the repository private, refuse anything else, guard every push.

`init` creates the GitHub repository through `gh` as **private**, refuses to
continue unless `gh repo view --json visibility` reports `PRIVATE`, makes the data
root its checkout, and installs a `pre-push` hook. The hook, and `push` and `pull`
in Python, re-check that:

- the push goes through `origin`, which has exactly one URL, the one recorded at init;
- no `pushurl` differs from it, and no `url.*.pushInsteadOf` rewrites it;
- that URL is one of the forms that name the recorded repository on github.com
  ([`github_urls()`](#acquaint.sync.github_urls), the same list the hook spells out);
- `gh` reports the repository, on github.com whatever `GH_HOST` says, as private.

The hook is installed in the repository’s shared hooks folder, executable, and
`core.hooksPath` points at it by absolute path, so linked worktrees are guarded too and
a global `core.hooksPath` cannot silently disable it. `init` takes over only an empty
folder, or a clone of that same repository; it refuses any other existing repository.

What this does **not** protect, stated plainly:

- a private repository is access control, not encryption: the host can read it all;
- `git push --no-verify` skips the hook;
- whoever can change this repository’s git config, or which `gh` runs on `PATH`,
  controls what the guard sees;
- moving the data root breaks the absolute hook path until `sync init
  --existing-only` runs again (`sync push` refuses in that state; a raw `git push`
  does not);
- file names and commit messages carry people’s names;
- deleting a folder does not remove it from history, other clones, or backups.

`git-remote-gcrypt`, which would encrypt contents, names and history, is not supported
yet: the guard does not recognise its internal push, so `init` refuses `gcrypt::` URLs.

Every `git` and `gh` call goes through `run`, so tests can script `gh` while
`git` runs for real.

### Functions

| [`github_urls`](#acquaint.sync.github_urls)(repo)                               | Every remote URL accepted for a GitHub repository.                                                                   |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| [`init`](#acquaint.sync.init)(root, repo, \*[, remote_url, create, ...]) | Make `root` a checkout of the private GitHub repository `repo`, creating it (private) if needed.                     |
| [`pull`](#acquaint.sync.pull)(root, \*[, dry_run, run])                  | Re-check the remote and its visibility, then rebase local work onto it (uncommitted edits are stashed and restored). |
| [`push`](#acquaint.sync.push)(root, \*[, message, dry_run, run])         | Commit everything, rebase onto the remote, and push, after re-checking the remote, the guard and the visibility.     |
| [`run_command`](#acquaint.sync.run_command)(args, \*[, cwd])                    | Run `git` or `gh` (`gh` pinned to github.com), capturing text output.                                                |
| [`status`](#acquaint.sync.status)(root, \*[, check_visibility, run])       | Whether the store is synced, where to, uncommitted changes, ahead/behind, the guard, and live visibility.            |
| [`visibility`](#acquaint.sync.visibility)(repo, \*[, run])                     | `PRIVATE`, `PUBLIC` or `INTERNAL`, as `gh` reports it now for the repository on github.com.                          |

### acquaint.sync.github_urls(repo)

Every remote URL accepted for a GitHub repository. The pre-push hook spells out the same six forms.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> github_urls("example/profiles")
['git@github.com:example/profiles.git', 'git@github.com:example/profiles', 'ssh://git@github.com/example/profiles.git', 'ssh://git@github.com/example/profiles', 'https://github.com/example/profiles.git', 'https://github.com/example/profiles']
```

### acquaint.sync.init(root, repo, \*, remote_url=None, create=True, dry_run=False, run=<function run_command>)

Make `root` a checkout of the private GitHub repository `repo`, creating it (private) if needed.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.sync.pull(root, \*, dry_run=False, run=<function run_command>)

Re-check the remote and its visibility, then rebase local work onto it (uncommitted edits are stashed and restored).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.sync.push(root, \*, message=None, dry_run=False, run=<function run_command>)

Commit everything, rebase onto the remote, and push, after re-checking the remote, the guard and the visibility.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.sync.run_command(args, , cwd=None)

Run `git` or `gh` (`gh` pinned to github.com), capturing text output.

* **Return type:**
  [`CompletedProcess`](https://docs.python.org/3/library/subprocess.html#subprocess.CompletedProcess)

### acquaint.sync.status(root, \*, check_visibility=True, run=<function run_command>)

Whether the store is synced, where to, uncommitted changes, ahead/behind, the guard, and live visibility.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### acquaint.sync.visibility(repo, \*, run=<function run_command>)

`PRIVATE`, `PUBLIC` or `INTERNAL`, as `gh` reports it now for the repository on github.com.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
