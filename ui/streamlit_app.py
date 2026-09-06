"""gitteam web UI entry point.

Run with:  streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

import services as svc

st.set_page_config(page_title="gitteam", page_icon=":material/hub:", layout="wide")

svc.init_state()

pages = [
    st.Page("app_pages/overview.py", title="概要", icon=":material/dashboard:", default=True),
    st.Page("app_pages/config_page.py", title="設定", icon=":material/settings:"),
    st.Page("app_pages/repo_page.py", title="リポジトリ", icon=":material/folder:"),
    st.Page("app_pages/team_page.py", title="チーム", icon=":material/group:"),
    st.Page("app_pages/ops_page.py", title="運用", icon=":material/account_tree:"),
    st.Page("app_pages/dev_page.py", title="開発者環境", icon=":material/computer:"),
]
page = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.text_input(
        "設定ファイル (gitteam.yaml)",
        key="cfg_path",
        help="空欄のまま Enter で自動探索した場所に戻ります。",
    )
    cfg, cfg_error = svc.load_config()
    if cfg:
        st.badge(f"{cfg.mode.value} / {cfg.owner}", icon=":material/check:", color="green")
    else:
        st.badge("設定未読込", icon=":material/warning:", color="orange")
    st.toggle("dry-run（変更を加えない）", key="dry_run", help="ON の間は git / gh の変更系コマンドを表示するだけで実行しません。")
    st.toggle("詳細ログ", key="verbose")
    st.caption("gitteam web UI")

st.title(page.title, icon=page.icon)
page.run()
