import streamlit as st

import glossary as gl
import services as svc
from gitteam.commands import team as team_cmd
from gitteam.config import PERMISSIONS, Mode

st.caption("設定ファイルに登録したチームとメンバーを GitHub に反映したり、新しい人を招待したりするページです。")

cfg, cfg_error = svc.load_config()
if cfg is None:
    st.warning("先に「はじめに」ページで設定ファイルを作成してください。", icon=":material/warning:")
    st.page_link("app_pages/start.py", label="はじめにページへ", icon=":material/flag:")
    st.stop()

is_org = cfg.mode is not Mode.PERSONAL

st.subheader("登録されているチーム" if is_org else "登録されている共同作業者", icon=":material/groups:")
if is_org:
    if cfg.teams:
        st.dataframe(
            [
                {
                    "チーム": t.name,
                    "権限": gl.PERMISSION_LABELS.get(t.permission, t.permission),
                    "メンテナー": ", ".join(t.maintainers) or "-",
                    "メンバー": ", ".join(t.members) or "-",
                    "対象リポジトリ": "すべて" if "*" in t.repos else ", ".join(t.repos),
                }
                for t in cfg.teams
            ],
            hide_index=True,
        )
    else:
        st.caption("チームがまだ登録されていません。")
    st.page_link("app_pages/config_page.py", label="チームやメンバーを追加・変更する", icon=":material/edit:")
if cfg.collaborators:
    st.dataframe(
        [
            {"ユーザー": c.user, "権限": gl.PERMISSION_LABELS.get(c.permission, c.permission), "対象リポジトリ": "すべて" if "*" in c.repos else ", ".join(c.repos)}
            for c in cfg.collaborators
        ],
        hide_index=True,
    )
elif not is_org:
    st.caption("共同作業者はまだ登録されていません。一人で使う場合はこのままで構いません。")
    st.page_link("app_pages/config_page.py", label="共同作業者を追加する", icon=":material/edit:")

st.subheader("GitHub に反映する", icon=":material/sync:")
st.caption(
    "登録内容どおりにチームを作り、メンバーを追加し、リポジトリの権限を付けます。何度実行しても同じ結果になります。"
    "まだ GitHub の組織に参加していない人には、GitHub から招待メールが届きます。",
    help=gl.help_text("team") if is_org else gl.help_text("collaborator"),
)
with st.form("team_sync"):
    repo_filter = st.text_input("対象のリポジトリを限定する（任意、カンマ区切り）", placeholder="空欄ならオーナーの全リポジトリ")
    skip_repos = st.toggle("チームとメンバーだけ反映し、リポジトリの権限は変えない", value=False)
    sync_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:")
if sync_submitted:
    repos = [r.strip() for r in repo_filter.split(",") if r.strip()] or None
    with st.spinner("確認中..."):
        svc.stage_action("team_sync", team_cmd.sync, repos, skip_repos)
svc.render_action("team_sync", execute_label="この内容で GitHub に反映する")

st.subheader("一人を招待する", icon=":material/person_add:")
st.caption("設定ファイルに登録せず、その場で一人だけ招待したいときに使います。")
with st.form("team_invite"):
    user = st.text_input("GitHub のユーザー名", placeholder="例: octocat")
    if is_org:
        team = st.selectbox("所属させるチーム（任意）", ["(なし)"] + [t.name for t in cfg.teams])
        role = st.segmented_control("組織での役割", ["member", "admin"], format_func=lambda v: "メンバー" if v == "member" else "組織の管理者", default="member")
    else:
        team, role = "(なし)", "member"
    repo = st.text_input(
        "リポジトリ名" + ("（任意。直接この人に権限を付ける場合）" if is_org else "（必須）"),
        placeholder="例: my-service",
    )
    permission = st.selectbox("リポジトリの権限", list(PERMISSIONS), index=PERMISSIONS.index("push"), format_func=gl.PERMISSION_LABELS.get, help=gl.help_text("permission"))
    invite_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:")
if invite_submitted:
    if not user.strip():
        st.error("ユーザー名を入力してください。")
    elif not is_org and not repo.strip():
        st.error("個人アカウントでは招待先のリポジトリ名が必要です。")
    else:
        with st.spinner("確認中..."):
            svc.stage_action(
                "team_invite",
                team_cmd.invite,
                user.strip(),
                None if team == "(なし)" else team,
                role or "member",
                repo.strip() or None,
                permission,
            )
svc.render_action("team_invite", execute_label="この内容で招待する")

st.subheader("GitHub 上の今の状態を見る", icon=":material/cloud:")
if st.button("チームとメンバーを取得する", icon=":material/download:"):
    with st.spinner("取得中..."):
        svc.run_direct("team_list", team_cmd.list_teams)
svc.render_direct("team_list", empty_hint="ボタンを押すと GitHub から現在の一覧を取得します。")
