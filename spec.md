# gitteam 仕様書

| 項目 | 内容 |
| --- | --- |
| 文書種別 | ソフトウェア仕様書（機能・非機能・セキュリティ） |
| 対象バージョン | 0.1.0（`main` ブランチ、2026-09-07 時点） |
| 対象読者 | 開発者、チーム管理者、レビュアー |
| 関連文書 | `README.md`（利用ガイド）、`SECURITY.md`（セキュリティポリシー）、`docs/publishing-checklist.md`（公開前確認）、`docs/manual.html`（取扱説明書） |

要求の強さは RFC 2119 に準じ、**MUST**（必須）/ **SHOULD**（推奨）/ **MAY**（任意）で表記する。

---

## 1. 目的と背景

チームで GitHub を使い始める際に必要な作業（リポジトリの標準化、チームとメンバーの権限、作業規約、各メンバーの PC 設定）は手順が多く、担当者の経験に依存しやすい。gitteam はこれらを **設定ファイル `gitteam.yaml` に記述したチーム標準として管理し、CLI と Web UI から冪等に適用する**ツールである。

### 1.1 設計目標

| ID | 目標 |
| --- | --- |
| G-1 | 個人アカウント / Organization（Free・Team）/ Organization（Enterprise Cloud）の 3 形態を同じ設定・同じ操作で扱える |
| G-2 | すべての変更操作は事前に「実行内容」を確認でき、確認だけでは何も変更しない |
| G-3 | 何度実行しても同じ結果になる（冪等） |
| G-4 | GitHub への接続と認証は `gh` CLI に委ね、gitteam 自身は認証情報を保持しない |
| G-5 | 初心者が用語を知らなくても Web UI の案内に従えば初期設定を完了できる |

### 1.2 対象外

* GitHub Enterprise Server（オンプレミス）
* リポジトリやチームの削除
* GitHub 以外のホスティング（GitLab、Bitbucket）

---

## 2. 用語

| 用語 | 定義 |
| --- | --- |
| オーナー（owner） | リポジトリを所有する GitHub アカウント。Organization 名または個人のログイン名 |
| 利用形態（mode） | `personal` / `org` / `org-enterprise` のいずれか |
| プラン（plan） | GitHub の料金プラン。`auto`（API から判定）/ `free` / `pro` / `team` / `enterprise` |
| 能力（capabilities） | mode × plan × 可視性から算出される「使える機能」の集合 |
| 雛形（scaffold） | 新規リポジトリに配置する標準ファイル一式 |
| 規約（conventions） | ブランチ命名、コミットメッセージ（Conventional Commits）、タグ形式のルール |
| dry-run | 変更系コマンドを実行せず、実行予定のコマンドと API ペイロードを表示する動作 |
| 信頼（trust） | 作業ディレクトリで発見した `gitteam.yaml` を使用してよいと利用者が明示した状態 |

---

## 3. システム構成

### 3.1 構成要素

```
gitteam/                 Python パッケージ（CLI とコアロジック）
├── cli.py               typer によるコマンド定義、共通オプション
├── context.py           1 回の実行で共有する状態（設定、Runner、Gh）
├── config.py            gitteam.yaml のスキーマ・読み込み・検証・探索・信頼管理
├── capabilities.py      能力マトリクスの算出
├── conventions.py       ブランチ名 / コミット / semver / PR タイトルの純粋関数
├── protection.py        ブランチ保護（Rulesets / classic）の API ペイロード生成
├── labels.py            ラベル差分の計画
├── scaffold.py          雛形の生成（string.Template）
├── runner.py            subprocess 実行基盤（dry-run / verbose）
├── gh.py, gitcmd.py     gh / git のラッパー
├── ui.py                rich 出力（差し替え可能なコンソール）
├── commands/            ユースケース（repo, team, ops, dev, doctor, config）
└── templates/           gitteam.example.yaml、scaffold/**
ui/                      Streamlit Web UI
├── streamlit_app.py     エントリ（st.navigation、サイドバー）
├── services.py          コマンド呼び出し、出力キャプチャ、確認→実行フロー、日本語要約
├── glossary.py          用語説明・表示ラベル
└── app_pages/           8 ページ
tests/                   pytest（160 件）
```

### 3.2 依存関係

| 種別 | 内容 |
| --- | --- |
| 実行環境 | Python 3.11 以上、git 2.23 以上、gh 2.47 以上（`gh auth login` 済み） |
| 必須パッケージ | typer, rich, pyyaml |
| UI 用パッケージ | streamlit 1.57 以上、ruamel.yaml 0.18 以上（コメント保持編集） |
| 開発用 | pytest |

### 3.3 レイヤ構造と責務

| レイヤ | モジュール | 責務 | 副作用 |
| --- | --- | --- | --- |
| インターフェース | `cli.py`, `ui/` | 入力の受付、結果の表示 | なし |
| ユースケース | `commands/*` | 手順の組み立て、能力による分岐 | Gh / Git 経由のみ |
| コア（純粋） | `config`, `capabilities`, `conventions`, `protection`, `labels`, `scaffold`（生成部） | 検証、計算、ペイロード生成 | なし（単体テスト対象） |
| 統合 | `runner`, `gh`, `gitcmd` | 外部コマンド実行 | あり |

**MUST**: 純粋レイヤは外部コマンドを呼び出してはならない。
**MUST**: 変更を伴う外部コマンドは `Runner.run(mutating=True)` を経由し、dry-run 時は実行せず表示のみ行う。

---

## 4. 設定ファイル `gitteam.yaml`

### 4.1 探索順序

| 順位 | 場所 | 信頼 |
| --- | --- | --- |
| 1 | `--config PATH` | 明示指定のため信頼 |
| 2 | 環境変数 `GITTEAM_CONFIG` | 信頼 |
| 3 | カレントディレクトリおよびその親ディレクトリの `gitteam.yaml` | **要信頼**（§7.2） |
| 4 | `~/.config/gitteam/gitteam.yaml`（`GITTEAM_CONFIG_HOME` で変更可）、`%APPDATA%\gitteam\gitteam.yaml` | 信頼 |

### 4.2 スキーマ

| キー | 型 / 既定値 | 説明 |
| --- | --- | --- |
| `owner` | string（必須） | GitHub ログイン名。`^[A-Za-z0-9][A-Za-z0-9-]{0,38}$` |
| `mode` | `org` | `personal` / `org` / `org-enterprise` |
| `plan` | `auto` | `auto` / `free` / `pro` / `team` / `enterprise` |
| `repo.visibility` | `private` | `private` / `public` / `internal`（internal は org-enterprise のみ） |
| `repo.default_branch` | `main` | 既定ブランチ名 |
| `repo.delete_branch_on_merge` ほかマージ設定 | 表 4.3 参照 | リポジトリ設定 |
| `repo.gitignore_templates` | `[]` | github/gitignore のテンプレート名 |
| `repo.license` | `null` | `gh api licenses` のキー（例 `mit`） |
| `labels` | 既定 17 種 | `name` / `color`（6 桁 hex）/ `description` |
| `protection.*` | 表 4.4 参照 | ブランチ保護 |
| `scaffold.enabled` / `include` / `codeowners` | 全コンポーネント有効 | 雛形の構成 |
| `teams[]` | `[]` | `name`, `description`, `privacy`, `members`, `maintainers`, `permission`, `repos` |
| `collaborators[]` | `[]` | `user`, `permission`, `repos` |
| `conventions.*` | 表 4.5 参照 | 作業規約 |
| `dev.git_config` / `aliases` / `line_endings` / `signing` / `shared_hooks` / `repos` | 表 4.6 参照 | 開発者 PC の設定 |

**MUST**: 未知のキーは読み込みエラーとする（タイプミス検出）。
**MUST**: `mode: personal` のとき `teams` は空でなければならない。

### 4.3 リポジトリ設定の既定値

| キー | 既定値 |
| --- | --- |
| `delete_branch_on_merge` | true |
| `allow_squash_merge` / `allow_merge_commit` / `allow_rebase_merge` | true / false / false |
| `allow_auto_merge` / `allow_update_branch` | true / true |
| `squash_merge_commit_title` / `squash_merge_commit_message` | `PR_TITLE` / `PR_BODY` |
| `has_issues` / `has_wiki` / `has_projects` | true / false / false |

### 4.4 ブランチ保護の既定値

| キー | 既定値 | 備考 |
| --- | --- | --- |
| `branches` | `[main]` | fnmatch パターン可（`release/*`）。パターンは Rulesets のみ |
| `engine` | `auto`（= ruleset） | `ruleset` / `classic` |
| `required_approvals` | 1 | 0〜6 |
| `dismiss_stale_reviews` / `require_code_owner_reviews` / `require_last_push_approval` | true / true / false | |
| `require_conversation_resolution` / `required_linear_history` / `require_signed_commits` | true / true / false | |
| `enforce_admins` | true | false のとき Rulesets では管理者ロールをバイパス対象に追加 |
| `status_checks` / `strict_status_checks` | `[]` / true | |
| `allow_force_pushes` / `allow_deletions` | false / false | |

### 4.5 規約の既定値

| キー | 既定値 |
| --- | --- |
| `branch_types` | feature, fix, hotfix, chore, docs, refactor, test, release |
| `branch_pattern` | `^(feature\|fix\|hotfix\|chore\|docs\|refactor\|test\|release)/[a-z0-9][a-z0-9._-]*$` |
| `protected_branches` | main, develop（命名規則の対象外） |
| `require_issue_in_branch` | false |
| `commit_types` | feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert |
| `commit_scopes` / `require_scope` | `[]` / false |
| `commit_subject_max` | 72 |
| `tag_prefix` | `v` |
| `pr_reviewers` | `[]` |
| `pr_labels_by_type` | feat→enhancement, fix→bug, docs→documentation, chore→chore |

### 4.6 開発者設定の既定値

| キー | 既定値 |
| --- | --- |
| `git_config` | init.defaultBranch=main, pull.rebase=true, fetch.prune=true, push.autoSetupRemote=true, rebase.autoStash=true, rerere.enabled=true, merge.conflictStyle=zdiff3, diff.algorithm=histogram, core.longpaths=true |
| `aliases` | st, co, sw, br, lg, last, unstage |
| `line_endings` | `auto`（Windows: `core.autocrlf=true`、他: `input`） |
| `signing` | `none`（`ssh` / `gpg`） |
| `shared_hooks` | true（`.githooks` を `core.hooksPath` で有効化） |
| `repos` | `[]`（`dev onboard` で clone する対象） |

---

## 5. 能力マトリクス

利用形態・プラン・可視性から機能の可否を算出し、使えない機能は**理由付きでスキップ**する。

| 機能 | personal / free | personal / pro | org / free | org / team | org-enterprise |
| --- | --- | --- | --- | --- | --- |
| チーム | × | × | ○ | ○ | ○ |
| ブランチ保護（public） | ○ | ○ | ○ | ○ | ○ |
| ブランチ保護（private） | × | ○ | × | ○ | ○ |
| CODEOWNERS レビュー強制 | ブランチ保護に準ずる | | | | |
| 組織レベル Rulesets / push rulesets / 必須ワークフロー | × | × | × | × | ○ |
| internal リポジトリ | × | × | × | × | ○ |

プランの自動判定は `gh api orgs/{owner}`（org）または `gh api user`（personal）の `plan.name` を用い、判定できない場合は `free` とみなして警告する。

---

## 6. 機能要件

### 6.1 CLI コマンド

| コマンド | 概要 | 要求 |
| --- | --- | --- |
| `doctor` | git / gh / 認証 / 設定 / オーナー種別 / プラン / チーム存在を点検し表で表示 | MUST |
| `config init` | コメント付き `gitteam.yaml` を生成し、生成したファイルを信頼リストに登録 | MUST |
| `config validate` / `show` / `capabilities` | 検証、既定値適用後の表示、能力表示 | MUST |
| `config trust` / `untrust` / `trusted` | 作業ディレクトリで見つけた設定の信頼登録・解除・一覧 | MUST |
| `repo init [NAME]` | 作成 → 雛形 → 設定 → ラベル → 保護 → 権限 を一括適用。引数なしはカレントのリポジトリ | MUST |
| `repo settings` / `labels sync [--prune]` / `protect` / `access` | 個別適用 | MUST |
| `team sync [--repo] [--skip-repos]` | チーム作成、メンバー追加、リポジトリ権限（personal ではコラボレーター） | MUST |
| `team invite USER [--team] [--role] [--repo] [--permission]` | 招待 | MUST |
| `team list` | GitHub 上のチームとメンバー | SHOULD |
| `ops branch new TYPE DESC [--issue] [--base]` | 規約に従うブランチ名を生成し、最新の base から作成 | MUST |
| `ops branch check [NAME]` | 命名規則の検証（違反時 exit 1） | MUST |
| `ops commit check [--range] [--message-file] [--message]` | Conventional Commits の検証（違反時 exit 1） | MUST |
| `ops pr create [--title] [--base] [--draft] [--reviewer] [--label] [--no-verify]` | プッシュ → テンプレート・ラベル・レビュアー付きで PR 作成 | MUST |
| `ops release VERSION [--prerelease] [--draft] [--allow-dirty]` | 既定ブランチで注釈付きタグと GitHub Release を作成 | MUST |
| `ops hooks install [--shared/--local]` | commit-msg / pre-push フックの配置 | MUST |
| `dev setup [--name] [--email] [--scope] [--signing-key] [--skip-gh]` | git 設定・エイリアス・改行コード・gh 認証ヘルパー | MUST |
| `dev onboard [--dir] [--name] [--email]` | setup + `dev.repos` の clone + hooks 有効化 | MUST |
| `dev show` | 現在の git 設定表示 | SHOULD |

共通オプション: `--config PATH`, `--dry-run` / `-n`, `--verbose` / `-v`, `--version`。

**MUST**: すべての変更系コマンドは `--dry-run` で実行予定の git / gh コマンドと JSON ペイロードを表示し、変更を加えない。
**MUST**: ユーザー向けエラー（`GitTeamError`）はトレースバックなしで表示し exit 1 とする。

### 6.2 `repo init` の処理

1. `gh api repos/{owner}/{name}` で存在確認。無ければ `gh repo create`。
2. 雛形: 作業ディレクトリを clone（または既存 clone を使用）し、`scaffold.include` のコンポーネントを生成。既存ファイルは `--force` がない限り保持。生成物があれば `chore: initial project scaffold` としてコミットしプッシュ（`--no-push` で抑止）。フックは `git update-index --chmod=+x` で実行権限を付与。
3. 設定: `PATCH repos/{o}/{r}`（マージ方式など）、トピック。
4. ラベル: 既存を取得し、作成 / 更新 / 保持（`--prune` で削除）を計画・適用。
5. 保護: 能力で可否を判定。Rulesets は `gitteam:<branch>` という名前で作成または更新、classic は既存ブランチにのみ適用。
6. 権限: `teams[]`（org）または `collaborators[]`（personal）のうち対象リポジトリに該当するものを付与。
7. 結果の要約表を表示。

雛形コンポーネント: `readme`, `gitignore`（github/gitignore を結合）, `license`, `editorconfig`, `gitattributes`, `codeowners`, `pr_template`, `issue_templates`, `contributing`, `workflows`（`conventions.yml`: ブランチ名・PR タイトル・コミット検証）, `githooks`（`commit-msg`, `pre-push`, `README.md`）。

### 6.3 規約の検証仕様

| 対象 | 規則 |
| --- | --- |
| ブランチ名 | `branch_pattern` に一致。`protected_branches` は対象外。`require_issue_in_branch` のとき `<type>/<issue>-<desc>` |
| コミット件名 | `<type>(<scope>)?!?: <description>`。type は `commit_types`、長さ ≤ `commit_subject_max`、末尾ピリオド禁止、2 行目は空行。`Merge `/`Revert "` 始まりは対象外。`fixup!`/`squash!` は違反 |
| バージョン | semver（`MAJOR.MINOR.PATCH[-pre][+build]`）。`tag_prefix` の有無を許容し、タグは `tag_prefix + semver` |
| PR タイトル | コミットが 1 件で規約準拠ならその件名、それ以外はブランチ名から `<type>: <words>` を生成 |

### 6.4 Web UI

| ページ | 機能 |
| --- | --- |
| はじめに | 4 ステップ（ツールとログイン → 設定ファイル → メンバー登録 → 最初のリポジトリ）を進み具合付きで案内。最小 2 項目で設定生成 |
| 状態を見る | 設定・ログイン・ツールのカード、環境診断、可視性ごとの能力表（日本語の項目名と説明） |
| チームの設定 | かんたん設定（フォーム、コメント保持）と詳細（YAML 編集・検証・保存） |
| PC のセットアップ | git 設定の適用、`dev.repos` の一括 clone、現在の設定表示 |
| リポジトリを作る | `repo init` のフォーム、既存リポジトリへの個別適用 |
| チームとメンバー | 登録内容の一覧、GitHub への反映、個別招待、現状取得 |
| 日々の作業 | ブランチ名ビルダー、コミットメッセージ検証、PR 作成、リリース、hooks 導入 |
| 用語集とよくある質問 | 用語 21 語と FAQ |

**MUST**: 変更を伴う操作は「内容を確認する」（dry-run 実行と操作一覧の日本語表示）→「この内容で実行する」の 2 段階とし、実行は確認時と同一の引数で行う。
**MUST**: dry-run 出力の各コマンド行を日本語の操作説明に変換して表示する（`services.describe_command`）。
**SHOULD**: エラーは原因別の日本語ヒントを添える（`services.friendly_error`）。

---

## 7. セキュリティ要件

### 7.1 脅威モデル

| 入力 | 扱い |
| --- | --- |
| CLI 引数・環境変数 | 信頼 |
| ユーザー設定ディレクトリの `gitteam.yaml` | 信頼 |
| 作業ディレクトリ（親含む）の `gitteam.yaml` | 明示的な信頼まで不使用 |
| GitHub API 応答 | 信頼（GitHub を信頼） |
| Web UI | ローカル専用、認証なし |

### 7.2 要件

| ID | 要件 | 強さ |
| --- | --- | --- |
| S-1 | Web UI は `localhost` のみで待ち受ける（`.streamlit/config.toml` と起動スクリプトで固定） | MUST |
| S-2 | UI から指定できる設定ファイルは「カレントディレクトリ配下」または「ユーザー設定ディレクトリ配下」の `.yaml` / `.yml` に限る | MUST |
| S-3 | UI は `owner` または `mode` を含む YAML マッピングのみを設定として表示・編集する | MUST |
| S-4 | 作業ディレクトリで発見した設定は `is_trusted` が真になるまで読み込まない。`config init` で作成した設定は自動的に信頼する | MUST |
| S-5 | `dev.git_config` のキーは許可リスト（`ALLOWED_GIT_CONFIG_KEYS`）のみ。エイリアスの値は `!` で始まってはならない | MUST |
| S-6 | フック / ワークフローに埋め込む値（`branch_pattern`、種別名、保護ブランチ名、タグ接頭辞、既定ブランチ名、リポジトリ名、テンプレート名、オーナー名）は安全な文字集合に制限する | MUST |
| S-7 | 外部コマンドはリスト引数で起動し `shell=True` を使わない。YAML は `safe_load` のみ | MUST |
| S-8 | 認証情報を保存・出力しない（gh に委ねる） | MUST |

---

## 8. 非機能要件

| 分類 | 要件 |
| --- | --- |
| 冪等性 | 同じ設定で繰り返し実行しても結果が変わらない（ラベル・Rulesets・チーム・権限は差分適用） |
| 可搬性 | Windows / macOS / Linux。改行コードは `.gitattributes` で LF に統一（bat / ps1 は CRLF） |
| 表示 | UI は日本語。CLI メッセージは英語（rich による色付き表・ルール） |
| テスト | pytest 160 件。純粋レイヤは外部コマンドなしで検証。UI は `st.testing.v1.AppTest` によるヘッドレステスト。GitHub への変更を伴うテストは行わない |
| 起動 | `start_ui.bat` / `.ps1` / `.sh` は初回に仮想環境作成と依存導入を行い、ブラウザを開く |
| ライセンス | MIT |

---

## 9. エラー処理

| 例外 | 意味 | 表示 |
| --- | --- | --- |
| `ConfigError` | 設定の欠落・不正 | 問題箇所を列挙 |
| `UntrustedConfigError` | 未信頼の設定を検出 | 信頼方法（`config trust`、`--config`）を案内 |
| `CommandError` / `GhApiError` | git / gh の失敗 | HTTP ステータスと GitHub のメッセージ |
| `CapabilityError` | 利用形態・プランで使えない操作 | 代替手段（コラボレーター等）を案内 |
| `ConventionError` | 規約違反 | 期待する形式の例を表示 |

---

## 10. 制約・前提・未決事項

### 10.1 前提

* 操作者は対象オーナーに対して十分な権限（リポジトリ作成、チーム管理には `admin:org` スコープ）を持つ。
* `gh` は既にログイン済みである。

### 10.2 既知の制約

* classic ブランチ保護は既存ブランチにのみ適用でき、パターンは扱えない（Rulesets を推奨）。
* Organization のプランはトークンの権限によっては取得できず、その場合は `free` と仮定する。
* Web UI は単一利用者のローカル利用を前提とし、複数人での同時利用や公開は想定しない。

### 10.3 未決事項

* CLI メッセージの日本語化（現状は UI の要約のみ日本語）。
* リポジトリ内 `gitteam.yaml` を信頼する際の内容差分表示。
* 組織レベル Rulesets の適用コマンド（Enterprise 向け）。
