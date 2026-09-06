# Shared git hooks

These hooks are versioned with the repository and enforce the team conventions locally,
before CI does:

| Hook | Checks |
| --- | --- |
| `commit-msg` | Conventional Commits subject, allowed types, max length |
| `pre-push` | Branch naming pattern, every pushed commit message |

Enable them once per clone:

```bash
git config core.hooksPath .githooks       # or: gitteam ops hooks install
```

If `gitteam` is on your PATH the hooks delegate to it (so they follow `gitteam.yaml`);
otherwise a POSIX `sh` fallback with the same rules runs.
