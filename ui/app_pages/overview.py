import streamlit as st

import services as svc
from gitteam.commands import doctor as doctor_cmd

cfg, cfg_error = svc.load_config()
versions = svc.tool_versions()
login = svc.gh_login()

cols = st.columns(4)
with cols[0].container(border=True, height="stretch"):
    st.caption("設定ファイル")
    if cfg:
        st.markdown(f"**{cfg.source_path.name}**")
        st.caption(str(cfg.source_path.parent))
    else:
        st.markdown(":orange-badge[未読込]")
        st.caption("「設定」ページで生成できます")
with cols[1].container(border=True, height="stretch"):
    st.caption("モード / オーナー")
    st.markdown(f"**{cfg.mode.value}**  \n{cfg.owner}" if cfg else ":orange-badge[未設定]")
with cols[2].container(border=True, height="stretch"):
    st.caption("gh ログイン")
    st.markdown(f"**{login}**" if login else ":red-badge[未認証]")
    st.caption(versions.get("gh") or "gh が見つかりません")
with cols[3].container(border=True, height="stretch"):
    st.caption("git")
    st.markdown(f"**{versions['git']}**" if versions.get("git") else ":red-badge[未検出]")

st.subheader("環境診断", icon=":material/stethoscope:")
st.caption("git / gh / 認証 / 設定 / プランと利用可能機能をまとめて確認します。GitHub API を数回呼び出します。")
if st.button("診断を実行", icon=":material/play_arrow:", type="primary"):
    with st.spinner("診断中..."):
        st.session_state.overview_doctor = svc.run_captured(doctor_cmd.run, svc.make_context(dry_run=True))
svc.render_result(st.session_state.get("overview_doctor"), empty_hint="「診断を実行」を押すと結果がここに表示されます。")

if cfg:
    st.subheader("利用可能な機能", icon=":material/verified:")
    visibility = st.segmented_control(
        "リポジトリの可視性", ["private", "public", "internal"], default=cfg.repo.visibility, key="overview_visibility"
    )
    if st.button("確認", icon=":material/search:"):
        with st.spinner("プランを確認中..."):
            ctx = svc.make_context(dry_run=True)
            result = svc.run_captured(lambda: ctx.capabilities(visibility or cfg.repo.visibility))
        st.session_state.overview_caps = result
    caps_result = st.session_state.get("overview_caps")
    if caps_result and caps_result.ok:
        rows = caps_result.value.as_rows()
        st.dataframe(
            [{"機能": name, "利用可否": value} for name, value in rows],
            hide_index=True,
            width="content",
        )
        for note in caps_result.value.notes:
            st.caption(note)
    elif caps_result:
        st.error(caps_result.error)

st.subheader("はじめかた", icon=":material/rocket_launch:")
st.markdown(
    """
1. **設定** ページで `gitteam.yaml` を生成し、owner / mode / チーム / 規約を編集する
2. **概要** の診断で認証とプランを確認する
3. **チーム** で Team とメンバーを同期する（org モード）
4. **リポジトリ** で dry-run の実行計画を確認してから適用する
5. **開発者環境** で新メンバーの git 設定とクローンを行う
"""
)
