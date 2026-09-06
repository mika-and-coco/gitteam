from pathlib import Path

import streamlit as st

import glossary as gl
import services as svc
from gitteam import config as cfgmod
from gitteam.commands import config_cmd

st.caption(
    "このアプリは、チームで GitHub を使い始めるときに必要な準備（メンバー、リポジトリ、作業ルール）を、"
    "画面から順番に済ませるためのものです。上から順に進めてください。"
)

versions = svc.tool_versions()
login = svc.gh_login()
cfg, cfg_error = svc.load_config()

step_tools = bool(versions.get("git") and versions.get("gh") and login)
step_config = cfg is not None
if cfg is None:
    step_members = False
elif cfg.mode.is_org:
    step_members = any(t.members or t.maintainers for t in cfg.teams)
else:
    step_members = True  # collaborators are optional for personal use
completed = sum([step_tools, step_config, step_config and step_members])
st.progress(completed / 3, text=f"準備の進み具合: {completed} / 3")


def status_badge(done: bool) -> None:
    if done:
        st.badge("完了", icon=":material/check:", color="green")
    else:
        st.badge("未完了", icon=":material/radio_button_unchecked:", color="gray")


# ---------------------------------------------------------------- step 1
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("1. 必要なツールと GitHub へのログイン")
        status_badge(step_tools)
    st.caption("このアプリは git と gh（GitHub の公式コマンド）を使って GitHub に接続します。")
    checks = [
        ("git", versions.get("git"), "https://git-scm.com/downloads からインストールしてください。"),
        ("gh（GitHub CLI）", versions.get("gh"), "https://cli.github.com/ からインストールしてください。"),
        ("GitHub へのログイン", f"{login} でログイン中" if login else None, "ターミナルで `gh auth login` を実行し、ブラウザの指示に従ってログインしてください。"),
    ]
    for name, value, fix in checks:
        if value:
            st.markdown(f"- :material/check_circle: **{name}**: {value}")
        else:
            st.markdown(f"- :material/cancel: **{name}**: 未検出。{fix}")
    if not step_tools and st.button("もう一度確認する", icon=":material/refresh:"):
        svc.refresh_environment()
        st.rerun()

# ---------------------------------------------------------------- step 2
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("2. チームの設定ファイルを作る")
        status_badge(step_config)
    if cfg:
        st.markdown(
            f"- 利用形態: **{gl.MODE_LABELS[cfg.mode.value]}**  \n"
            f"- オーナー: **{cfg.owner}**  \n"
            f"- 保存場所: `{cfg.source_path}`"
        )
        st.page_link("app_pages/config_page.py", label="設定を見直す・変更する", icon=":material/settings:")
    else:
        if cfg_error and svc.config_path().is_file():
            st.error(cfg_error, icon=":material/error:")
        st.caption(
            "設定ファイル（gitteam.yaml）には「誰のアカウントで」「どんなルールで」使うかを書きます。"
            "ここでは最低限の 2 項目だけ決めれば作成でき、あとから画面で変更できます。"
        )
        with st.form("start_config"):
            mode_value = st.radio(
                "GitHub をどのように使いますか？",
                list(gl.MODE_LABELS),
                format_func=gl.MODE_LABELS.get,
                index=0 if not login else 0,
                help=gl.help_text("mode"),
                captions=[
                    "自分のアカウントの下にリポジトリを作り、共同作業者を個別に招待します。",
                    "会社やサークルの Organization を使い、チーム単位で権限を管理します。",
                    "GitHub Enterprise Cloud の Organization を使います（内部公開リポジトリなどが使えます）。",
                ],
            )
            owner = st.text_input(
                "オーナー（GitHub のアカウント名）",
                value=login or "",
                key="start_owner",
                help=gl.help_text("owner"),
                placeholder="組織名 または 自分のユーザー名",
            )
            st.caption(
                f"個人で使うなら自分のユーザー名（{login or '例: octocat'}）、組織で使うなら組織名"
                "（`https://github.com/<ここ>` の部分）を入力します。"
            )
            output = st.text_input("保存場所", value=str(svc.config_path()), key="start_output")
            submitted = st.form_submit_button("設定ファイルを作成する", type="primary", icon=":material/add:")
        if submitted:
            if not owner.strip():
                st.error("オーナーを入力してください。")
            else:
                result = svc.run_captured(
                    config_cmd.init,
                    svc.make_context(dry_run=False),
                    owner.strip(),
                    cfgmod.Mode(mode_value),
                    Path(output).expanduser(),
                    False,
                )
                if result.ok:
                    st.session_state.pending_cfg_path = output
                    st.toast("設定ファイルを作成しました", icon=":material/check:")
                    st.rerun()
                svc.render_summary(result, planned=False)

# ---------------------------------------------------------------- step 3
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("3. メンバーを登録する")
        status_badge(step_config and step_members)
    if cfg is None:
        st.caption("先にステップ 2 を完了してください。")
    elif cfg.mode.is_org:
        registered = sum(len(set(t.members) | set(t.maintainers)) for t in cfg.teams)
        st.caption(
            f"チームごとにメンバーの GitHub ユーザー名を登録し、リポジトリへの権限をまとめて付けます。"
            f"現在 {len(cfg.teams)} チーム、{registered} 人が登録されています。"
        )
        st.page_link("app_pages/config_page.py", label="「チームの設定」でメンバーを登録する", icon=":material/group_add:")
        st.page_link("app_pages/team_page.py", label="登録内容を GitHub に反映する（チームとメンバー）", icon=":material/sync:")
    else:
        st.caption(
            f"個人アカウントでは、共同作業者をリポジトリごとに招待します（現在 {len(cfg.collaborators)} 人）。"
            "一人で使う場合はこのステップは不要です。"
        )
        st.page_link("app_pages/config_page.py", label="共同作業者を登録する", icon=":material/person_add:")

# ---------------------------------------------------------------- step 4
with st.container(border=True):
    st.subheader("4. 最初のリポジトリを作る")
    st.caption(
        "リポジトリ名を入れるだけで、作成・標準ファイルの配置・ラベル・main ブランチの保護・メンバーへの権限付与までを一度に行います。"
        "実行前に「これから行う操作」を必ず確認できます。"
    )
    if cfg:
        st.page_link("app_pages/repo_page.py", label="リポジトリを作る", icon=":material/create_new_folder:")
    else:
        st.caption("先にステップ 2 を完了してください。")

st.subheader("困ったときは", icon=":material/help:")
st.page_link("app_pages/glossary_page.py", label="用語集とよくある質問を見る", icon=":material/menu_book:")
st.page_link("app_pages/overview.py", label="環境の診断を実行する", icon=":material/stethoscope:")
