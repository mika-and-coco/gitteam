from pathlib import Path

import streamlit as st

import services as svc
from gitteam import config as cfgmod
from gitteam.commands import dev as dev_cmd

cfg, _ = svc.load_config()
dev_cfg = (cfg or cfgmod.default_config()).dev
global_dry = svc.dry_run_notice()

st.subheader("git 設定のセットアップ", icon=":material/build:")
st.caption("チーム標準の git config・エイリアス・改行コード・gh 認証ヘルパーを適用します。")
with st.expander("適用される内容", icon=":material/list:"):
    st.dataframe(
        [{"キー": k, "値": v} for k, v in dev_cfg.git_config.items()]
        + [{"キー": f"alias.{k}", "値": v} for k, v in dev_cfg.aliases.items()]
        + [{"キー": "core.autocrlf", "値": f"({dev_cfg.line_endings}: OS により決定)"}],
        hide_index=True,
    )

with st.form("dev_setup"):
    cols = st.columns(2)
    name = cols[0].text_input("user.name", placeholder="Taro Yamada")
    email = cols[1].text_input("user.email", placeholder="taro@example.com")
    scope = st.segmented_control("適用範囲", ["global", "local"], default="global", help="local はこの UI を起動したディレクトリのリポジトリに適用します。")
    signing_key = st.text_input("署名鍵（SSH 公開鍵パス または GPG 鍵 ID、任意）")
    skip_gh = st.toggle("gh 認証の設定をスキップ", value=False)
    with st.container(horizontal=True):
        setup_plan = st.form_submit_button("計画を表示（dry-run）", icon=":material/visibility:")
        setup_apply = st.form_submit_button("適用", type="primary", icon=":material/check:")
if setup_plan or setup_apply:
    dry = True if setup_plan else global_dry
    st.session_state.dev_setup_result = svc.run_captured(
        dev_cmd.setup,
        svc.make_context(dry_run=dry),
        name=name.strip() or None,
        email=email.strip() or None,
        scope=scope or "global",
        signing_key=signing_key.strip() or None,
        skip_gh=skip_gh,
    )
svc.render_result(st.session_state.get("dev_setup_result"))

st.subheader("新メンバーのオンボーディング", icon=":material/person_add:")
if cfg is None:
    st.caption("設定ファイルが必要です（dev.repos に clone 対象を列挙します）。")
else:
    st.caption(f"セットアップに加えて dev.repos（{len(dev_cfg.repos)} 件）を clone し、hooks を有効化します。")
    with st.form("dev_onboard"):
        directory = st.text_input("clone 先ディレクトリ", value=str(Path.home() / "work"))
        cols = st.columns(2)
        ob_name = cols[0].text_input("user.name", key="ob_name")
        ob_email = cols[1].text_input("user.email", key="ob_email")
        ob_skip_gh = st.toggle("gh 認証の設定をスキップ", value=False, key="ob_skip_gh")
        onboard_clicked = st.form_submit_button("オンボーディングを実行", type="primary", icon=":material/rocket_launch:")
    if onboard_clicked:
        with st.spinner("実行中..."):
            st.session_state.dev_onboard_result = svc.run_captured(
                dev_cmd.onboard,
                svc.make_context(),
                directory=Path(directory).expanduser(),
                name=ob_name.strip() or None,
                email=ob_email.strip() or None,
                skip_gh=ob_skip_gh,
            )
    svc.render_result(st.session_state.get("dev_onboard_result"))

st.subheader("現在の git 設定", icon=":material/visibility:")
if st.button("表示", icon=":material/refresh:"):
    st.session_state.dev_show_result = svc.run_captured(dev_cmd.show, svc.make_context(dry_run=True))
svc.render_result(st.session_state.get("dev_show_result"), empty_hint="")
