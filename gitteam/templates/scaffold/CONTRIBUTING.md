# Contributing to $repo

This document describes the team workflow enforced by `gitteam`, the shared git hooks in
`.githooks/`, and the `Conventions` GitHub Actions workflow.

## 1. Set up your environment

```bash
gitteam dev setup --name "Your Name" --email you@example.com   # git config, aliases, gh auth
gitteam ops hooks install                                     # enable .githooks for this clone
```

Without `gitteam` installed: `git config core.hooksPath .githooks`.

## 2. Branching

* Always start from an up-to-date `$default_branch`.
* Branch names must match `$branch_pattern`.
* Allowed types: $branch_types.
* Create a branch with `gitteam ops branch new feature "short description" [--issue 123]`.

## 3. Commits

Commit subjects follow **Conventional Commits**:

```
<type>(<optional scope>): <description>

[optional body]

[optional footer, e.g. Closes #123 or BREAKING CHANGE: ...]
```

* Types: $commit_types
* Subject length: at most $commit_subject_max characters, no trailing period.
* Use `!` after the type/scope for breaking changes: `feat(api)!: drop v1 endpoints`.

## 4. Pull requests

* Open a PR against `$default_branch` (`gitteam ops pr create`).
* The PR title must itself be a valid Conventional Commit subject (it becomes the squash commit).
* Keep PRs focused; link the issue with `Closes #N`.
* CODEOWNERS reviewers are requested automatically; resolve every review thread before merging.

## 5. Releases

```bash
gitteam ops release 1.4.0        # tags ${tag_prefix}1.4.0 on $default_branch and publishes a GitHub Release
```

Release notes are generated from merged pull requests.
