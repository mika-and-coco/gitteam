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
    cfg, _ = svc.load_config()
    if cfg:
        st.badge(f"設定済み: {cfg.owner}", icon=":material/check:", color="green")
    else:
        st.badge("設定はまだありません", icon=":material/info:", color="orange")
    with st.expander("上級者向け", icon=":material/tune:"):
        st.text_input("設定ファイルの場所", key="cfg_path", help="通常は変更不要です。別の gitteam.yaml を使うときだけ指定します。")
        st.toggle("詳細ログを表示する", key="verbose", help="実行した git / gh コマンドをすべて詳細ログに出します。")
    st.caption("すべての操作は「内容を確認する」→「実行する」の 2 段階です。確認だけなら何も変更されません。")

st.title(page.title, icon=page.icon)
page.run()
