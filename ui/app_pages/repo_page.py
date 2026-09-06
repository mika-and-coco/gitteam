from pathlib import Path

import streamlit as st

import glossary as gl
import services as svc
from gitteam.commands import repo as repo_cmd

st.caption(
    "新しいリポジトリを作り、チームの標準（雛形ファイル・ラベル・main の保護・メンバーの権限）を一度に適用します。"
    "すでにあるリポジトリに標準を当て直すこともできます。"
)

cfg, cfg_error = svc.load_config()
if cfg is None:
    st.warning("先に「はじめに」ページで設定ファイルを作成してください。", icon=":material/warning:")
    st.page_link("app_pages/start.py", label="はじめにページへ", icon=":material/flag:")
    st.stop()

st.subheader("新しいリポジトリを作る", icon=":material/create_new_folder:")
st.caption(f"作成先: **{cfg.owner}**（{gl.MODE_LABELS[cfg.mode.value]}）。まず「内容を確認する」で、行われる操作の一覧を見てから実行します。")

with st.form("repo_init"):
    left, right = st.columns([2, 1])
    name = left.text_input("リポジトリ名", placeholder="例: my-service（半角英数字とハイフン）", help=gl.help_text("repository"))
    visibility = right.segmented_control(
        "公開範囲",
        list(gl.VISIBILITY_LABELS),
        format_func=gl.VISIBILITY_LABELS.get,
        default=cfg.repo.visibility,
        key="repo_visibility",
        help=gl.help_text("visibility"),
    )
    description = st.text_input("説明（任意）", placeholder="このリポジトリが何のためのものか一言で")
    steps = st.pills(
        "行うこと",
        list(gl.STEP_LABELS),
        format_func=gl.STEP_LABELS.get,
        selection_mode="multi",
        default=list(gl.STEP_LABELS),
        help=f"{gl.help_text('scaffold')}\n\n{gl.help_text('labels')}\n\n{gl.help_text('branch_protection')}",
    )
    with st.expander("詳しい設定", icon=":material/tune:"):
        directory = st.text_input(
            "PC 上でクローンする場所",
            value=str(Path.cwd()),
            help="この場所の下に <リポジトリ名> というフォルダーを作り、雛形ファイルを入れてコミット・プッシュします。",
        )
        push = st.toggle("雛形ファイルをコミットしてプッシュする", value=True)
        force = st.toggle("既にある雛形ファイルを上書きする", value=False)
    submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:")

if submitted:
    if not name.strip():
        st.error("リポジトリ名を入力してください。")
    else:
        selected = set(steps or [])
        opts = repo_cmd.InitOptions(
            name=name.strip(),
            visibility=visibility,
            description=description or None,
            directory=Path(directory).expanduser() / name.strip() if directory else None,
            scaffold="scaffold" in selected,
            settings="settings" in selected,
            labels="labels" in selected,
            protect="protect" in selected,
            access="access" in selected,
            push=push,
            force=force,
        )
        with st.spinner("確認中..."):
            svc.stage_action("repo_init", repo_cmd.init_repo, opts)
svc.render_action("repo_init", execute_label="この内容でリポジトリを作成・設定する")

st.subheader("すでにあるリポジトリに標準を適用する", icon=":material/tune:")
ACTIONS = {
    "settings": "マージ方式などの設定を揃える",
    "labels": "ラベルを揃える",
    "protect": "main ブランチを保護する",
    "access": "チーム / メンバーに権限を付ける",
}


def _apply_single(ctx, target_name: str, action: str, prune: bool) -> None:
    target = repo_cmd.resolve_target(ctx, target_name)
    if action == "settings":
        repo_cmd.apply_settings(ctx, target)
    elif action == "labels":
        repo_cmd.sync_labels(ctx, target, prune)
    elif action == "protect":
        data = ctx.gh.repo_get(target.owner, target.name)
        visibility_ = str(data.get("visibility", "private")) if data else ctx.config.repo.visibility
        repo_cmd.apply_protection(ctx, target, visibility_)
    elif action == "access":
        repo_cmd.apply_access(ctx, target)


with st.form("repo_single"):
    target_name = st.text_input("リポジトリ名", placeholder=f"例: my-service（{cfg.owner} の下にあるもの）")
    action = st.segmented_control("行うこと", list(ACTIONS), format_func=ACTIONS.get, default="labels")
    prune = st.toggle("設定にないラベルは削除する（ラベルを揃えるときのみ）", value=False)
    single_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:")

if single_submitted:
    if not target_name.strip():
        st.error("リポジトリ名を入力してください。")
    else:
        with st.spinner("確認中..."):
            svc.stage_action("repo_single", _apply_single, target_name.strip(), action or "labels", prune)
svc.render_action("repo_single")
