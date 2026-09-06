# gitteam

Git / GitHub のチーム初期設定と日常運用を 1 つの CLI にまとめたツールです。
`gh` CLI と `git` をラップし、設定ファイル `gitteam.yaml` に書いたチーム標準を
リポジトリ・チーム・開発者環境へ冪等に適用します。

| 領域 | コマンド | 内容 |
| --- | --- | --- |
| リポジトリ初期設定 | `gitteam repo init` | リポジトリ作成、雛形ファイル、マージ設定、ラベル、ブランチ保護、権限付与 |
| チーム・権限 | `gitteam team sync` / `invite` / `list` | Team 作成、メンバー追加、リポジトリ権限、コラボレーター招待 |
| 日常運用 | `gitteam ops ...` | ブランチ命名、Conventional Commits 検証、PR 作成、リリース、git hooks |
| 開発者環境 | `gitteam dev setup` / `onboard` | git config・エイリアス・改行コード・gh 認証、リポジトリ一括 clone |
| 診断 | `gitteam doctor` / `config capabilities` | 前提ツール、認証、設定、プランごとの利用可能機能 |

## 対応する GitHub 利用形態

`mode` を切り替えるだけで、同じ設定ファイル・コマンドが 3 形態で動作します。
利用できない機能は実行前に検出し、理由付きでスキップします。

| `mode` | 想定 | Team | ブランチ保護 (private) | Rulesets | internal リポジトリ |
| --- | --- | --- | --- | --- | --- |
| `org` | Organization（Free / Team プラン） | あり | Team プラン以上 | Team プラン以上 | なし |
| `org-enterprise` | Organization（Enterprise Cloud） | あり | あり | あり（org レベルも） | あり |
| `personal` | 個人アカウント配下 | なし（collaborators で代替） | Pro プラン以上 | Pro プラン以上 | なし |

> public リポジトリではプランに関係なくブランチ保護 / Rulesets が使えます。
> プランは `plan: auto` で GitHub API から自動判定します（読めない場合は `plan:` で明示）。

## インストール

前提: Python 3.11+、`git` 2.23+、`gh` 2.44+（`gh auth login` 済み）。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  /  macOS, Linux: source .venv/bin/activate
pip install -e ".[dev]"
gitteam --version
```

## クイックスタート

```bash
# 1. 設定ファイルを生成（コメント付き）し、内容を確認
gitteam config init --owner my-org --mode org
gitteam doctor                     # git / gh / 認証 / 設定 / プラン能力を確認

# 2. チームとメンバーを同期（org モード）
gitteam team sync --dry-run        # 実行内容を確認
gitteam team sync

# 3. リポジトリを作成して全設定を適用
gitteam repo init my-service --description "Order service"

# 4. 新メンバーのオンボーディング
gitteam dev onboard --name "Taro Yamada" --email taro@example.com --dir ~/work

# 5. 日常運用
gitteam ops branch new feature "add login page" --issue 42   # -> feature/42-add-login-page
gitteam ops commit check                                      # origin/main..HEAD を検証
gitteam ops pr create --draft
gitteam ops release 1.4.0
```

すべてのコマンドは `--dry-run`（`-n`）に対応し、実行される `git` / `gh` コマンドと
API ペイロードを表示するだけで変更を加えません。`--verbose`（`-v`）で実行コマンドを表示します。

## `gitteam repo init` の処理内容

1. **リポジトリ作成**: 存在しなければ `gh repo create`。既存なら設定の適用のみ。
2. **雛形の配置とコミット**: clone 先に以下を生成し `chore: initial project scaffold` としてプッシュ。
   `README.md` / `.gitignore`（github/gitignore テンプレートを結合）/ `LICENSE` / `.editorconfig` /
   `.gitattributes` / `.github/CODEOWNERS` / PR テンプレート / Issue フォーム / `CONTRIBUTING.md` /
   `.github/workflows/conventions.yml`（ブランチ名・PR タイトル・コミット検証）/ `.githooks/`（commit-msg, pre-push）
3. **リポジトリ設定**: squash マージのみ許可、マージ後ブランチ削除、auto-merge、Wiki/Projects 無効 など。
4. **ラベル同期**: 設定のラベルセットを作成・更新（`--prune` で不要ラベル削除）。
5. **ブランチ保護**: Rulesets（推奨、パターン対応）または classic branch protection。
   レビュー必須数、CODEOWNERS レビュー、会話解決、線形履歴、force-push / 削除禁止、必須ステータスチェック。
6. **権限付与**: 設定の Team（org）またはコラボレーター（personal）に権限を付与。

既存リポジトリの clone 内で引数なしに実行すると、そのリポジトリに設定を適用します。
個別に実行したい場合は `repo settings` / `repo labels sync` / `repo protect` / `repo access` を使います。

## 設定ファイル `gitteam.yaml`

`gitteam config init` が全キーにコメント付きのファイルを生成します。探索順は
`--config` → 環境変数 `GITTEAM_CONFIG` → カレントから親方向の `gitteam.yaml` →
`~/.config/gitteam/gitteam.yaml` → `%APPDATA%\gitteam\gitteam.yaml` です。

```yaml
owner: my-org
mode: org                # org | org-enterprise | personal
plan: auto

repo:
  visibility: private
  default_branch: main
  gitignore_templates: [Python, Node]
  license: mit

protection:
  branches: [main, "release/*"]
  engine: auto           # auto(=ruleset) | ruleset | classic
  required_approvals: 1
  require_code_owner_reviews: true
  status_checks: ["Branch / PR title / commits"]

teams:
  - name: core
    maintainers: [alice]
    members: [bob, carol]
    permission: maintain
    repos: ["*"]

conventions:
  branch_pattern: '^(feature|fix|hotfix|chore|docs|refactor|test|release)/[a-z0-9][a-z0-9._-]*$'
  commit_types: [feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert]
  commit_subject_max: 72
  tag_prefix: v
  pr_reviewers: ["my-org/core"]

dev:
  line_endings: auto     # Windows は core.autocrlf=true、それ以外は input
  repos: [my-service, my-web]
```

## 規約の多層防御

| 層 | 仕組み | 効果 |
| --- | --- | --- |
| ローカル | `.githooks/commit-msg`, `pre-push`（`gitteam ops hooks install`） | コミット時・push 時に即座に検出 |
| CLI | `gitteam ops branch check` / `commit check` / `pr create` | PR 作成前に検証、タイトル・ラベル・レビュアーを自動設定 |
| CI | `.github/workflows/conventions.yml` | `gitteam` 未導入の環境でもブロック |
| サーバー | Rulesets / branch protection | レビュー・CODEOWNERS・線形履歴を強制 |

hooks は `gitteam` が PATH にあればそれを呼び、無い場合は同じルールの POSIX sh 実装で動作します。

## 必要な gh トークンスコープ

| 操作 | スコープ |
| --- | --- |
| リポジトリ作成・設定・ラベル・保護 | `repo` |
| Team 作成・メンバー・権限 | `admin:org`（`gh auth refresh -s admin:org`） |
| プラン自動判定（org） | `read:org` |

## 開発

```bash
pip install -e ".[dev]"
pytest                    # 113 tests: 設定、能力マトリクス、規約、ペイロード、雛形、CLI、Web UI
```

構成:

| モジュール | 責務 |
| --- | --- |
| `gitteam/cli.py` | typer によるコマンド定義、共通オプション |
| `gitteam/config.py` | `gitteam.yaml` の読み込み・検証（未知キー検出） |
| `gitteam/capabilities.py` | mode × plan × visibility から利用可能機能を算出 |
| `gitteam/conventions.py` | ブランチ名 / コミット / semver / PR タイトルの純粋関数 |
| `gitteam/protection.py`, `labels.py` | API ペイロード生成、ラベル差分計画 |
| `gitteam/gh.py`, `gitcmd.py`, `runner.py` | `gh api` / `git` ラッパー、dry-run 実行基盤 |
| `gitteam/scaffold.py`, `templates/` | 雛形生成（`$var` 置換） |
| `gitteam/commands/` | 各ユースケース（repo / team / ops / dev / doctor / config） |

## Web UI（Streamlit）

CLI と同じ `commands/` 層をブラウザから操作できる画面です。サイドバーの **dry-run** トグルが既定で ON になっており、OFF にして確認チェックを入れない限り GitHub に変更は加わりません。

```bash
pip install -e ".[ui]"
streamlit run ui/streamlit_app.py
```

| ページ | 内容 |
| --- | --- |
| 概要 | 設定・gh ログイン・ツールの状態、環境診断（doctor）、プランごとの利用可能機能 |
| 設定 | `gitteam.yaml` の生成、YAML エディタでの編集・検証・保存、有効値の確認 |
| リポジトリ | `repo init` のフォーム実行（ステップ選択、計画表示 / 適用）、既存リポジトリへの個別適用 |
| チーム | 設定済みチーム / コラボレーターの一覧、同期、招待、GitHub 上の現状取得 |
| 運用 | ブランチ名ビルダー・検証、コミットメッセージ検証、PR 作成、リリース、hooks 導入 |
| 開発者環境 | git 設定セットアップ、新メンバーのオンボーディング、現在の設定表示 |

構成: `ui/streamlit_app.py`（エントリ、`st.navigation`）、`ui/app_pages/`（各ページ）、`ui/services.py`（コマンド呼び出しと rich 出力のキャプチャ）。
ヘッドレステストは `tests/test_ui.py`（`st.testing.v1.AppTest`）にあります。
