# 公開前チェックリスト（リポジトリを public にする前に）

このリポジトリを公開する際に「含めてよいもの」「含めてはいけないもの」の一覧と、確認手順です。

## 公開してよいもの（コミット対象）

| 種類 | 例 | 備考 |
| --- | --- | --- |
| ソースコード | `gitteam/`, `ui/`, `tests/` | 秘密情報を含まないことを確認済み |
| 雛形・設定例 | `gitteam/templates/**`（`gitteam.example.yaml` を含む） | 実在のユーザー名・組織名は含めない |
| ドキュメント | `README.md`, `SECURITY.md`, `docs/`, `LICENSE` | |
| 起動スクリプト | `start_ui.bat`, `start_ui.ps1`, `start_ui.sh` | `--server.address localhost` を必ず維持 |
| プロジェクト設定 | `pyproject.toml`, `.gitignore`, `.gitattributes`, `.streamlit/config.toml` | `config.toml` に secrets を書かない |

## 公開してはいけないもの（`.gitignore` 済み）

| 種類 | パス | 理由 |
| --- | --- | --- |
| 実際のチーム設定 | `gitteam.yaml`, `*.local.yaml` | 組織名・メンバーの GitHub ユーザー名・リポジトリ名を含む |
| 信頼済み設定の一覧 | `~/.config/gitteam/trusted-configs.txt`（リポジトリ外） | ローカルのパス情報 |
| Streamlit の秘密情報 | `.streamlit/secrets.toml` | |
| 認証情報・鍵 | `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `hosts.yml` | gh / SSH / API のトークン類 |
| 仮想環境・キャッシュ | `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/` | |
| ログ・スクリーンショット | `*.log`, `screenshots/` | 画面キャプチャに個人名やパスが写り込む |
| エディタ設定 | `.idea/`, `.vscode/` | |

## 公開直前の確認手順

```bash
# 1. 追跡されているファイルに秘密情報らしきものがないか
git ls-files | grep -i -E "secret|\.env|hosts\.yml|\.pem|\.key$|gitteam\.yaml$"

# 2. 履歴全体にトークンや秘密鍵が含まれていないか
git log -p --all | grep -n -i -E "gho_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_|BEGIN (RSA|OPENSSH) PRIVATE"

# 3. テストがすべて通ること
pytest

# 4. 雛形にサンプル以外の実名が入っていないこと
grep -rn -i "mika-and-coco\|nikam" gitteam/ ui/ --include=*.py --include=*.yaml --include=*.md
```

いずれも何も出力されなければ公開可能です。`LICENSE` の著作権者名は公開前に確認してください。

## コミットの作者情報について

コミットにはメールアドレスが記録され、公開後は誰でも閲覧できます。
非公開にしたい場合は、GitHub の **Settings → Emails → "Keep my email addresses private"** を有効にし、
表示される `<ID>+<user>@users.noreply.github.com` を `git config --global user.email` に設定してから
以降のコミットを行ってください（過去のコミットの書き換えは履歴の共有状況を確認のうえ判断してください）。

## 公開後に有効化すると良い GitHub 機能

* Security → **Private vulnerability reporting**（`SECURITY.md` の報告先）
* Security → **Secret scanning** と **Push protection**
* Settings → Branches / Rules → `main` の保護（`gitteam repo protect` でも設定可能）
