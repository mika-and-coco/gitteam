from pathlib import Path

import streamlit as st

import glossary as gl
import services as svc
from gitteam import config as cfgmod
from gitteam.commands import dev as dev_cmd

st.caption("新しく参加した人の PC に、チーム共通の git 設定を入れ、必要なリポジトリを取得するページです。各メンバーが自分の PC で 1 回行います。")

cfg, _ = svc.load_config()
dev_cfg = (cfg or cfgmod.default_config()).dev

st.subheader("git の設定をチーム標準に合わせる", icon=":material/build:")
st.caption("名前とメールアドレスに加え、改行コードや pull の挙動などチームで揃えておくべき設定と、便利な短縮コマンドを登録します。")
with st.expander("登録される設定を見る", icon=":material/list:"):
    st.dataframe(
        [{"設定": k, "値": v} for k, v in dev_cfg.git_config.items()]
        + [{"設定": f"alias.{k}（短縮コマンド）", "値": v} for k, v in dev_cfg.aliases.items()]
        + [{"設定": "core.autocrlf（改行コード）", "値": "OS に合わせて自動設定"}],
        hide_index=True,
    )

with st.form("dev_setup"):
    cols = st.columns(2)
    name = cols[0].text_input("名前（コミットに記録されます）", placeholder="例: Taro Yamada")
    email = cols[1].text_input("メールアドレス（GitHub に登録したもの）", placeholder="例: taro@example.com")
    with st.expander("詳しい設定", icon=":material/tune:"):
        scope = st.segmented_control(
            "適用範囲",
            ["global", "local"],
            format_func=lambda v: "この PC 全体（通常はこちら）" if v == "global" else "今いるリポジトリだけ",
            default="global",
        )
        signing_key = st.text_input("コミット署名用の鍵（任意。SSH 公開鍵のパスか GPG 鍵 ID）")
        skip_gh = st.toggle("gh のログイン設定には触れない", value=False)
    setup_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:")
if setup_submitted:
    svc.stage_action(
        "dev_setup",
        dev_cmd.setup,
        name=name.strip() or None,
        email=email.strip() or None,
        scope=scope or "global",
        signing_key=signing_key.strip() or None,
        skip_gh=skip_gh,
    )
svc.render_action("dev_setup", execute_label="この内容で git を設定する")

st.subheader("チームのリポジトリをまとめて取得する", icon=":material/download:")
if cfg is None:
    st.caption("設定ファイルがあると、登録されたリポジトリをまとめてクローンできます。")
elif not dev_cfg.repos:
    st.caption("取得するリポジトリが登録されていません。「チームの設定」の「PC のセットアップで自動的にクローンするリポジトリ」に追加してください。")
    st.page_link("app_pages/config_page.py", label="チームの設定へ", icon=":material/settings:")
else:
    st.caption(f"上の git 設定に加えて、{len(dev_cfg.repos)} 個のリポジトリ（{', '.join(dev_cfg.repos)}）をクローンし、自動チェック（hooks）を有効にします。")
    with st.form("dev_onboard"):
        directory = st.text_input("クローン先のフォルダー", value=str(Path.home() / "work"))
        cols = st.columns(2)
        ob_name = cols[0].text_input("名前", key="ob_name")
        ob_email = cols[1].text_input("メールアドレス", key="ob_email")
        ob_skip_gh = st.toggle("gh のログイン設定には触れない", value=False, key="ob_skip_gh")
        onboard_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:")
    if onboard_submitted:
        with st.spinner("確認中..."):
            svc.stage_action(
                "dev_onboard",
                dev_cmd.onboard,
                directory=Path(directory).expanduser(),
                name=ob_name.strip() or None,
                email=ob_email.strip() or None,
                skip_gh=ob_skip_gh,
            )
    svc.render_action("dev_onboard", execute_label="セットアップとクローンを実行する")

st.subheader("今の git 設定を見る", icon=":material/visibility:")
if st.button("表示する", icon=":material/refresh:"):
    svc.run_direct("dev_show", dev_cmd.show)
svc.render_direct("dev_show")
