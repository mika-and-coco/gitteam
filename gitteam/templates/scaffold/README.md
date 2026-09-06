# $repo

> Bootstrapped with `gitteam`. Replace this section with a description of the project.

## Development workflow

| Topic | Rule |
| --- | --- |
| Default branch | `$default_branch` (protected, changes land via pull request) |
| Branch names | `<type>/<short-description>` where type is one of: $branch_types |
| Commit messages | [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <description>` (types: $commit_types) |
| Releases | Annotated tag `${tag_prefix}MAJOR.MINOR.PATCH` + GitHub Release |

See [CONTRIBUTING.md](CONTRIBUTING.md) for details. To enable the shared git hooks locally:

```bash
git config core.hooksPath .githooks
```
