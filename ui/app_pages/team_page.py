import streamlit as st

import services as svc
from gitteam.commands import team as team_cmd
from gitteam.config import PERMISSIONS, Mode

cfg, cfg_error = svc.load_config()
if cfg is None:
    st.warning(cfg_error or "設定が必要です。", icon=":material/warning:")
    st.page_link("app_pages/config_page.py", label="設定ページへ", icon=":material/settings:")
    st.stop()

global_dry = svc.dry_run_notice()
is_org = cfg.mode is not Mode.PERSONAL

st.subheader("設定されているチーム" if is_org else "設定されているコラボレーター", icon=":material/groups:")
if is_org:
    if cfg.teams:
        st.dataframe(
            [
                {
                    "チーム": t.name,
                    "権限": t.permission,
                    "公開範囲": t.privacy,
                    "メンテナー": ", ".join(t.maintainers) or "-",
                    "メンバー": ", ".join(t.members) or "-",
                    "対象リポジトリ": ", ".join(t.repos),
                }
                for t in cfg.teams
            ],
            hide_index=True,
        )
    else:
        st.caption("teams: が空です。「設定」ページで追加してください。")
if cfg.collaborators:
    st.dataframe(
        [{"ユーザー": c.user, "権限": c.permission, "対象リポジトリ": ", ".join(c.repos)} for c in cfg.collaborators],
        hide_index=True,
    )
elif not is_org:
    st.caption("collaborators: が空です。「設定」ページで追加してください。")

st.subheader("同期", icon=":material/sync:")
st.caption("チーム作成、メンバー追加、リポジトリ権限を設定どおりに揃えます（冪等）。未参加ユーザーには GitHub から招待メールが送られます。")
with st.form("team_sync"):
    repo_filter = st.text_input("対象リポジトリを限定（カンマ区切り、空欄で全リポジトリ）", placeholder="my-service, my-web")
    skip_repos = st.toggle("チームとメンバーのみ（リポジトリ権限は触らない）", value=False)
    with st.container(horizontal=True):
        sync_plan = st.form_submit_button("計画を表示（dry-run）", icon=":material/visibility:")
        sync_apply = st.form_submit_button("同期を適用", type="primary", icon=":material/sync:")
if sync_plan or sync_apply:
    repos = [r.strip() for r in repo_filter.split(",") if r.strip()] or None
    dry = True if sync_plan else global_dry
    with st.spinner("同期中..."):
        st.session_state.team_sync_result = svc.run_captured(team_cmd.sync, svc.make_context(dry_run=dry), repos, skip_repos)
svc.render_result(st.session_state.get("team_sync_result"))

st.subheader("招待", icon=":material/person_add:")
with st.form("team_invite"):
    user = st.text_input("GitHub ログイン名")
    if is_org:
        team_options = ["(なし)"] + [t.name for t in cfg.teams]
        team = st.selectbox("チーム", team_options)
        role = st.segmented_control("Organization ロール", ["member", "admin"], default="member")
    else:
        team, role = "(なし)", "member"
    repo = st.text_input("リポジトリ（直接コラボレーター権限を付ける場合）", placeholder="personal モードでは必須")
    permission = st.selectbox("リポジトリ権限", list(PERMISSIONS), index=PERMISSIONS.index("push"))
    invite_clicked = st.form_submit_button("招待", type="primary", icon=":material/send:")
if invite_clicked:
    if not user.strip():
        st.error("ログイン名を入力してください。")
    else:
        st.session_state.team_invite_result = svc.run_captured(
            team_cmd.invite,
            svc.make_context(),
            user.strip(),
            None if team == "(なし)" else team,
            role or "member",
            repo.strip() or None,
            permission,
        )
svc.render_result(st.session_state.get("team_invite_result"))

st.subheader("GitHub 上の現状", icon=":material/cloud:")
if st.button("チームとメンバーを取得", icon=":material/download:"):
    with st.spinner("取得中..."):
        st.session_state.team_list_result = svc.run_captured(team_cmd.list_teams, svc.make_context(dry_run=True))
svc.render_result(st.session_state.get("team_list_result"), empty_hint="ボタンを押すと GitHub API から取得します。")
