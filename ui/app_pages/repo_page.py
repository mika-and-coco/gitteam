from pathlib import Path

import streamlit as st

import services as svc
from gitteam.commands import repo as repo_cmd

cfg, cfg_error = svc.load_config()
if cfg is None:
    st.warning(cfg_error or "設定が必要です。", icon=":material/warning:")
    st.page_link("app_pages/config_page.py", label="設定ページへ", icon=":material/settings:")
    st.stop()

STEP_LABELS = {
    "scaffold": "雛形ファイル",
    "settings": "リポジトリ設定",
    "labels": "ラベル",
    "protect": "ブランチ保護",
    "access": "権限付与",
}

st.subheader("リポジトリ初期化", icon=":material/create_new_folder:")
st.caption(f"オーナー **{cfg.owner}**（{cfg.mode.value}）配下に作成、または既存リポジトリへ設定を適用します。")
global_dry = svc.dry_run_notice()

with st.form("repo_init"):
    left, right = st.columns([2, 1])
    name = left.text_input("リポジトリ名", placeholder="my-service")
    visibility = right.segmented_control(
        "可視性", ["private", "public", "internal"], default=cfg.repo.visibility, key="repo_visibility"
    )
    description = st.text_input("説明", placeholder="任意")
    directory = st.text_input(
        "クローン / 雛形の配置先", value=str(Path.cwd()), help="この直下に <リポジトリ名> ディレクトリを作成します。"
    )
    steps = st.pills(
        "実行するステップ",
        list(STEP_LABELS),
        format_func=STEP_LABELS.get,
        selection_mode="multi",
        default=list(STEP_LABELS),
    )
    with st.container(horizontal=True):
        push = st.toggle("雛形をコミットしてプッシュ", value=True)
        force = st.toggle("既存の雛形ファイルを上書き", value=False)
    confirm = st.checkbox("GitHub とローカルに変更を加えることを理解しました（適用時に必須）")
    with st.container(horizontal=True):
        plan_clicked = st.form_submit_button("実行計画を表示（dry-run）", icon=":material/visibility:")
        apply_clicked = st.form_submit_button("適用", type="primary", icon=":material/rocket_launch:")

if plan_clicked or apply_clicked:
    if not name.strip():
        st.error("リポジトリ名を入力してください。")
    elif apply_clicked and not confirm:
        st.error("適用するには確認チェックを入れてください。")
    else:
        dry = True if plan_clicked else global_dry
        if apply_clicked and global_dry:
            st.warning("サイドバーの dry-run が ON のため、計画のみ表示します。", icon=":material/visibility:")
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
        with st.status("実行中...", expanded=False) as status:
            result = svc.run_captured(repo_cmd.init_repo, svc.make_context(dry_run=dry), opts)
            status.update(label="完了" if result.ok else "エラー", state="complete" if result.ok else "error")
        st.session_state.repo_result = result

svc.render_result(st.session_state.get("repo_result"))

st.subheader("既存リポジトリへの個別適用", icon=":material/tune:")
ACTIONS = {
    "settings": "リポジトリ設定",
    "labels": "ラベル同期",
    "protect": "ブランチ保護",
    "access": "権限付与",
}
with st.form("repo_single"):
    target_name = st.text_input("リポジトリ名（owner/name も可）", placeholder="my-service")
    action = st.segmented_control("操作", list(ACTIONS), format_func=ACTIONS.get, default="labels")
    prune = st.toggle("設定にないラベルを削除する（ラベル同期のみ）", value=False)
    with st.container(horizontal=True):
        single_plan = st.form_submit_button("計画を表示（dry-run）", icon=":material/visibility:")
        single_apply = st.form_submit_button("適用", type="primary", icon=":material/check:")

if single_plan or single_apply:
    if not target_name.strip():
        st.error("リポジトリ名を入力してください。")
    else:
        dry = True if single_plan else global_dry
        ctx = svc.make_context(dry_run=dry)

        def _run_single() -> None:
            target = repo_cmd.resolve_target(ctx, target_name.strip())
            if action == "settings":
                repo_cmd.apply_settings(ctx, target)
            elif action == "labels":
                repo_cmd.sync_labels(ctx, target, prune)
            elif action == "protect":
                data = ctx.gh.repo_get(target.owner, target.name)
                visibility_ = str(data.get("visibility", "private")) if data else cfg.repo.visibility
                repo_cmd.apply_protection(ctx, target, visibility_)
            elif action == "access":
                repo_cmd.apply_access(ctx, target)

        with st.spinner("実行中..."):
            st.session_state.repo_single_result = svc.run_captured(_run_single)

svc.render_result(st.session_state.get("repo_single_result"))
