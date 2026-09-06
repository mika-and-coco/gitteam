import streamlit as st

import glossary as gl
import services as svc
from gitteam.commands import doctor as doctor_cmd

st.caption("今の環境と設定の状態を確認するページです。何かがうまく動かないときは、まず「診断を実行」を押してください。")

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
        st.markdown(":orange-badge[未作成]")
        st.caption("「はじめに」ページで作成できます")
with cols[1].container(border=True, height="stretch"):
    st.caption("利用形態 / オーナー")
    st.markdown(f"**{gl.MODE_LABELS[cfg.mode.value]}**  \n{cfg.owner}" if cfg else ":orange-badge[未設定]")
with cols[2].container(border=True, height="stretch"):
    st.caption("GitHub へのログイン")
    st.markdown(f"**{login}**" if login else ":red-badge[未ログイン]")
    st.caption(versions.get("gh") or "gh が見つかりません")
with cols[3].container(border=True, height="stretch"):
    st.caption("git")
    st.markdown(f"**{versions['git']}**" if versions.get("git") else ":red-badge[未検出]")

st.subheader("環境診断", icon=":material/stethoscope:")
st.caption("git / gh / ログイン / 設定ファイル / GitHub のプランをまとめて点検します。GitHub に問い合わせるため数秒かかります。")
with st.container(horizontal=True):
    if st.button("診断を実行", icon=":material/play_arrow:", type="primary"):
        with st.spinner("診断中..."):
            svc.refresh_environment()
            svc.run_direct("overview_doctor", doctor_cmd.run)
svc.render_direct("overview_doctor", empty_hint="「診断を実行」を押すと結果がここに表示されます。")

if cfg:
    st.subheader("使える機能の確認", icon=":material/verified:")
    st.caption("GitHub のプランとリポジトリの可視性によって、使える機能が変わります。", help=gl.help_text("plan"))
    visibility = st.segmented_control(
        "リポジトリの可視性",
        list(gl.VISIBILITY_LABELS),
        format_func=gl.VISIBILITY_LABELS.get,
        default=cfg.repo.visibility,
        key="overview_visibility",
        help=gl.help_text("visibility"),
    )
    if st.button("確認する", icon=":material/search:"):
        with st.spinner("プランを確認中..."):
            ctx = svc.make_context(dry_run=True)
            st.session_state.overview_caps = svc.run_captured(lambda: ctx.capabilities(visibility or cfg.repo.visibility))
    caps_result = st.session_state.get("overview_caps")
    if caps_result and caps_result.ok:
        st.dataframe(
            [{"機能": name, "使える": "はい" if value == "yes" else ("いいえ" if value == "no" else value)} for name, value in caps_result.value.as_rows()],
            hide_index=True,
            width="content",
        )
        for note in caps_result.value.notes:
            st.caption(note)
    elif caps_result:
        st.error(svc.friendly_error(caps_result.error) or caps_result.error)
