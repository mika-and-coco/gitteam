# Security Policy / セキュリティポリシー

## 対象と前提（Threat model）

gitteam は **開発者の PC 上でローカルに動かす**ツールです。GitHub へのアクセスはすべて `gh` CLI に委ね、
gitteam 自身はトークンや認証情報を保存・送信しません。

| 入力 | 扱い |
| --- | --- |
| CLI の引数・環境変数 | 信頼する（操作者本人が指定） |
| `gitteam.yaml`（ユーザーの設定ディレクトリ配下） | 信頼する |
| `gitteam.yaml`（作業ディレクトリやその親で見つかったもの） | **明示的に信頼するまで使用しない**（`gitteam config trust`、UI の「この設定ファイルを信頼する」）。クローンしたリポジトリに同梱された設定が git 設定や生成フックを変えることを防ぐため |
| GitHub API の応答 | GitHub を信頼する |
| Web UI（Streamlit） | **localhost のみで待ち受け**、認証なし。ネットワークに公開しないこと |

## 組み込みの防御

* **設定値の検証**: 生成される git hooks / GitHub Actions に埋め込まれる値（ブランチ命名の正規表現、種別名、保護ブランチ名など）は安全な文字集合に制限し、シェルやYAMLへの注入を防ぎます。
* **git 設定のホワイトリスト**: `dev.git_config` に書けるキーは、git にプログラムを実行させないものだけです（`core.fsmonitor`、`core.sshCommand`、`credential.helper`、`core.hooksPath`、`!` で始まるエイリアスなどは拒否）。
* **UI の設定ファイルパス制限**: 画面から指定できる設定ファイルは、プロジェクト配下またはユーザーの設定ディレクトリ配下の `.yaml` に限られ、gitteam の設定として読める内容のときだけ表示します。
* **確認→実行の 2 段階**: 変更を伴う操作は常に dry-run の計画を先に表示します。
* **サブプロセス**: `git` / `gh` はすべてリスト引数で起動し、`shell=True` は使いません。YAML は `safe_load` のみです。

## 利用者へのお願い

* Web UI を `--server.address 0.0.0.0` などで LAN に公開しないでください。
* 他人のリポジトリ内で `gitteam` を実行するときは、同梱の `gitteam.yaml` を読んでから `gitteam config trust` してください。
* 例外: 副作用のない `ops branch check` / `ops commit check`（git hooks から呼ばれる）は、未信頼の `gitteam.yaml` でも
  `conventions` のみを読んで検証します（警告を表示）。フック自体がリポジトリ由来のコードであるため、信頼面は増えません。
* `gh auth login` のトークンは gh が管理します。gitteam の設定ファイルやリポジトリにトークンを書かないでください。

## 脆弱性の報告 / Reporting a vulnerability

公開 Issue ではなく、GitHub の **Private vulnerability reporting**（リポジトリの Security タブ →
"Report a vulnerability"）からご連絡ください。再現手順、影響、可能であれば修正案を添えてください。
Please use GitHub private vulnerability reporting instead of a public issue. Include reproduction steps and impact.

## サポート対象バージョン

| バージョン | 対応 |
| --- | --- |
| `main` の最新 | セキュリティ修正を提供 |
| それ以前のタグ | 最新版への更新をお願いします |
