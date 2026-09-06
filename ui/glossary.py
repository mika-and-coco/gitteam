"""Plain-language explanations of the terms used across the UI."""

from __future__ import annotations

# key -> (label shown to the user, one-paragraph explanation)
TERMS: dict[str, tuple[str, str]] = {
    "owner": (
        "オーナー",
        "リポジトリを所有する GitHub アカウントです。URL `https://github.com/<オーナー>/<リポジトリ>` の "
        "`<オーナー>` 部分にあたります。組織で使うなら組織名、個人で使うなら自分のユーザー名です。",
    ),
    "mode": (
        "利用形態",
        "GitHub を「個人アカウント」「組織（Organization）」「組織（GitHub Enterprise）」のどれで使うかです。"
        "形態によって使える機能（チーム、非公開リポジトリのブランチ保護など）が変わります。",
    ),
    "plan": (
        "プラン",
        "GitHub の料金プランです。無料プランでは非公開リポジトリにブランチ保護を設定できないなどの制限があります。"
        "このアプリは自動でプランを調べ、使えない機能は理由を添えてスキップします。",
    ),
    "repository": ("リポジトリ", "プロジェクトのファイルと変更履歴をまとめて保管する場所です。"),
    "visibility": (
        "可視性",
        "リポジトリを誰が見られるかです。private=関係者のみ、public=誰でも閲覧可、internal=組織内の全員（Enterprise のみ）。",
    ),
    "default_branch": (
        "既定ブランチ（main）",
        "完成したコードが集まる本流のブランチです。直接書き換えず、必ずプルリクエスト経由で変更を取り込みます。",
    ),
    "branch_protection": (
        "ブランチ保護（Rulesets）",
        "main ブランチを守るルールです。「レビュー承認がないとマージできない」「履歴の書き換え禁止」などを GitHub 側が強制します。",
    ),
    "codeowners": (
        "CODEOWNERS",
        "ファイルやフォルダごとの担当者を書いたファイルです。プルリクエストを出すと担当者が自動でレビュアーに指名されます。",
    ),
    "labels": ("ラベル", "Issue やプルリクエストに付ける色付きのタグです（bug、enhancement など）。分類と優先度付けに使います。"),
    "team": ("チーム", "組織内のメンバーをまとめたグループです。チーム単位でリポジトリの権限を付けられます。"),
    "collaborator": ("コラボレーター", "個人アカウントのリポジトリに招待された共同作業者です。組織のチームの代わりに使います。"),
    "permission": (
        "権限",
        "pull=閲覧のみ、triage=Issue の整理まで、push=コードの書き込み、maintain=一部の設定変更、admin=すべての操作。"
        "通常の開発者は push、リーダーは maintain が目安です。",
    ),
    "scaffold": (
        "雛形ファイル",
        "README、.gitignore、プルリクエストのテンプレート、CI の設定、git hooks など、新しいリポジトリに最初から入れておく標準ファイル一式です。",
    ),
    "conventional_commits": (
        "コミットメッセージの規約",
        "`feat: ログイン画面を追加` のように「種類: 説明」の形で書くルール（Conventional Commits）です。"
        "履歴が読みやすくなり、リリースノートを自動生成できます。種類は feat（機能追加）、fix（バグ修正）、docs、chore などです。",
    ),
    "branch_naming": (
        "ブランチ命名規則",
        "`feature/42-add-login` のように「種類/説明」で付けるルールです。何の作業か一目で分かり、Issue 番号と結び付けられます。",
    ),
    "hooks": (
        "git hooks",
        "コミットや push の直前に自動で走るチェックです。規約に合わないコミットメッセージやブランチ名をその場で止めます。",
    ),
    "pr": (
        "プルリクエスト（PR）",
        "自分のブランチの変更を main に取り込んでほしいという依頼です。レビューを受けてからマージ（統合）します。",
    ),
    "release": ("リリース", "バージョン番号のタグ（v1.2.0 など）を付け、変更点をまとめて公開することです。"),
    "gh": (
        "gh（GitHub CLI）",
        "ターミナルから GitHub を操作する公式ツールです。このアプリは gh を通して GitHub に接続するため、"
        "事前に `gh auth login` でログインしておく必要があります。",
    ),
    "dry_run": (
        "内容の確認（お試し実行）",
        "実際には何も変更せず、「これから行う操作の一覧」だけを表示します。このアプリでは必ず確認を挟んでから実行します。",
    ),
    "squash_merge": (
        "squash マージ",
        "プルリクエストの複数コミットを 1 つにまとめて main に取り込む方式です。main の履歴が 1 PR = 1 コミットで読みやすくなります。",
    ),
}

MODE_LABELS = {
    "personal": "個人アカウントで使う",
    "org": "組織（Organization）で使う",
    "org-enterprise": "組織（GitHub Enterprise）で使う",
}
VISIBILITY_LABELS = {
    "private": "非公開（private）",
    "public": "公開（public）",
    "internal": "組織内のみ（internal）",
}
PERMISSION_LABELS = {
    "pull": "pull（閲覧のみ）",
    "triage": "triage（Issue 整理）",
    "push": "push（書き込み）",
    "maintain": "maintain（一部設定）",
    "admin": "admin（すべて）",
}
# Rows of Capabilities.as_rows(): english key -> (Japanese name, explanation)
CAPABILITY_INFO: dict[str, tuple[str, str]] = {
    "mode": ("利用形態", "設定ファイルの mode。個人 / 組織 / 組織（Enterprise）のどれで使っているか。"),
    "plan": ("GitHub のプラン", "GitHub から自動判定した料金プラン。free は無料、pro / team / enterprise は有料プランです。"),
    "visibility": ("リポジトリの可視性", "この確認で想定したリポジトリの公開範囲。上の選択で切り替えられます。"),
    "teams": ("チーム機能", "組織のチームを作ってまとめて権限を付けられるか。個人アカウントでは使えず、コラボレーターの個別招待になります。"),
    "branch protection / rulesets": (
        "main ブランチの保護",
        "レビュー必須・強制プッシュ禁止などのルールを GitHub 側で強制できるか。非公開リポジトリでは有料プランが必要です。",
    ),
    "CODEOWNERS enforcement": (
        "担当者レビューの強制",
        "CODEOWNERS に書いた担当者の承認がないとマージできないようにできるか。ブランチ保護が使える場合に有効になります。",
    ),
    "org-level rulesets": ("組織全体のルール", "組織のすべてのリポジトリに共通のブランチ保護ルールを一括で適用できるか（Enterprise のみ）。"),
    "push rulesets": ("プッシュ内容の制限", "特定のファイルや拡張子のプッシュを組織全体で禁止できるか（Enterprise のみ）。"),
    "required workflows": ("必須ワークフロー", "すべてのリポジトリで必ず実行される CI（GitHub Actions）を組織で強制できるか（Enterprise のみ）。"),
    "internal repositories": ("組織内公開リポジトリ", "組織のメンバー全員には見えるが外部には非公開の internal リポジトリを作れるか（Enterprise のみ）。"),
}

STEP_LABELS = {
    "scaffold": "雛形ファイルを入れる",
    "settings": "マージ方式などの設定",
    "labels": "ラベルを揃える",
    "protect": "main ブランチを保護する",
    "access": "チーム / メンバーに権限を付ける",
}


def label(key: str) -> str:
    return TERMS[key][0]


def explain(key: str) -> str:
    return TERMS[key][1]


def help_text(key: str) -> str:
    """Text for a widget's ``help=`` tooltip."""
    name, description = TERMS[key]
    return f"**{name}** - {description}"


def rows() -> list[dict[str, str]]:
    return [{"用語": name, "意味": description} for name, description in TERMS.values()]
