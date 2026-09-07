"""gitteam web UI entry point.

Run with:  streamlit run ui/streamlit_app.py   (or double-click start_ui.bat)
"""

from __future__ import annotations

import streamlit as st

import services as svc

st.set_page_config(page_title="gitteam", page_icon=":material/hub:", layout="wide")

svc.init_state()

page = st.navigation(
    {
        "": [
            st.Page("app_pages/start.py", title="はじめに", icon=":material/flag:", default=True),
            st.Page("app_pages/overview.py", title="状態を見る", icon=":material/dashboard:"),
        ],
        "設定": [
            st.Page("app_pages/config_page.py", title="チームの設定", icon=":material/settings:"),
            st.Page("app_pages/dev_page.py", title="PC のセットアップ", icon=":material/computer:"),
        ],
        "運用": [
            st.Page("app_pages/repo_page.py", title="リポジトリを作る", icon=":material/folder:"),
            st.Page("app_pages/team_page.py", title="チームとメンバー", icon=":material/group:"),
            st.Page("app_pages/ops_page.py", title="日々の作業", icon=":material/account_tree:"),
        ],
        "ヘルプ": [
            st.Page("app_pages/glossary_page.py", title="用語集とよくある質問", icon=":material/help:"),
        ],
    },
    position="sidebar",
)

with st.sidebar:
    cfg, cfg_error = svc.load_config()
    if cfg:
        st.badge(f"設定済み: {cfg.owner}", icon=":material/check:", color="green")
    else:
        location_problem = svc.check_config_path(svc.config_path())
        status = "blocked" if location_problem else svc.trust_status(svc.config_path())
        if status == "blocked":
            st.badge("この場所の設定は使えません", icon=":material/block:", color="red")
            st.caption(location_problem)
        elif status == "untrusted":
            st.badge("未信頼の設定ファイル", icon=":material/gpp_maybe:", color="orange")
            st.caption(
                "このフォルダーにある gitteam.yaml は、あなたが作成したものではない可能性があります。"
                "内容を確認してから信頼してください。"
            )
            if st.button("この設定ファイルを信頼する", icon=":material/verified_user:"):
                svc.trust_current_config()
                st.rerun()
        elif status == "missing":
            st.badge("設定はまだありません", icon=":material/info:", color="orange")
        else:
            st.badge("設定を読み込めません", icon=":material/error:", color="red")
            st.caption(cfg_error or "")
    with st.expander("上級者向け", icon=":material/tune:"):
        st.text_input("設定ファイルの場所", key="cfg_path", help="通常は変更不要です。別の gitteam.yaml を使うときだけ指定します。")
        st.toggle("詳細ログを表示する", key="verbose", help="実行した git / gh コマンドをすべて詳細ログに出します。")
    st.caption("すべての操作は「内容を確認する」→「実行する」の 2 段階です。確認だけなら何も変更されません。")

st.title(page.title, icon=page.icon)
page.run()
