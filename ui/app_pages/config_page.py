from pathlib import Path

import streamlit as st

import services as svc
from gitteam import config as cfgmod
from gitteam.commands import config_cmd

path = svc.config_path()
cfg, cfg_error = svc.load_config()

if not path.is_file():
    st.info(f"`{path}` はまだありません。以下から生成できます。", icon=":material/info:")
    with st.form("config_init"):
        owner = st.text_input("オーナー（Organization または ユーザーのログイン名）", placeholder="my-org")
        mode = st.segmented_control(
            "GitHub の利用形態",
            [m.value for m in cfgmod.Mode],
            default=cfgmod.Mode.ORG.value,
            help="org: Free/Team プランの Organization、org-enterprise: Enterprise Cloud、personal: 個人アカウント",
        )
        output = st.text_input("出力先", value=str(path))
        submitted = st.form_submit_button("設定ファイルを生成", type="primary", icon=":material/add:")
    if submitted:
        if not owner.strip():
            st.error("オーナーを入力してください。")
        else:
            result = svc.run_captured(
                config_cmd.init,
                svc.make_context(dry_run=False),
                owner.strip(),
                cfgmod.Mode(mode or cfgmod.Mode.ORG.value),
                Path(output).expanduser(),
                False,
            )
            if result.ok:
                st.session_state.pending_cfg_path = output
                st.toast("設定ファイルを生成しました", icon=":material/check:")
                st.rerun()
            svc.render_result(result)
    st.stop()


def _reload_editor() -> None:
    st.session_state.pop("config_editor", None)


file_text = path.read_text(encoding="utf-8")
if cfg_error:
    st.error(cfg_error, icon=":material/error:")
else:
    st.caption(f":material/description: {path}")

st.text_area("gitteam.yaml", value=file_text, key="config_editor", height=520, label_visibility="collapsed")
editor_text = st.session_state.get("config_editor", file_text)

with st.container(horizontal=True):
    validate_clicked = st.button("検証", icon=":material/rule:")
    save_clicked = st.button("保存", icon=":material/save:", type="primary")
    st.button("ファイルから再読み込み", icon=":material/refresh:", on_click=_reload_editor)

if validate_clicked or save_clicked:
    parsed, error = svc.validate_yaml_text(editor_text)
    if error:
        st.error(error, icon=":material/error:")
    else:
        st.success(f"有効な設定です（owner={parsed.owner}, mode={parsed.mode.value}）", icon=":material/check_circle:")
        if save_clicked:
            path.write_text(editor_text, encoding="utf-8", newline="\n")
            st.toast("保存しました", icon=":material/save:")
            st.rerun()

if cfg:
    with st.expander("有効な設定（既定値を適用した結果）", icon=":material/visibility:"):
        st.code(svc.effective_yaml(cfg), language="yaml")
    with st.expander("設定サマリー", icon=":material/summarize:"):
        summary = st.columns(3)
        summary[0].metric("チーム数", len(cfg.teams))
        summary[1].metric("ラベル数", len(cfg.labels))
        summary[2].metric("保護ブランチ", ", ".join(cfg.protection.branches) or "-")
        st.dataframe(
            [
                {"ラベル": label.name, "色": f"#{label.color}", "説明": label.description}
                for label in cfg.labels
            ],
            hide_index=True,
        )

with st.expander("別の場所に新しい設定ファイルを生成", icon=":material/add_circle:"):
    with st.form("config_init_other"):
        owner2 = st.text_input("オーナー", key="init_other_owner")
        mode2 = st.segmented_control("利用形態", [m.value for m in cfgmod.Mode], default="org", key="init_other_mode")
        output2 = st.text_input("出力先", value=str(Path.home() / ".config" / "gitteam" / "gitteam.yaml"))
        force2 = st.checkbox("既存ファイルを上書きする")
        if st.form_submit_button("生成", icon=":material/add:"):
            if not owner2.strip():
                st.error("オーナーを入力してください。")
            else:
                result = svc.run_captured(
                    config_cmd.init,
                    svc.make_context(dry_run=False),
                    owner2.strip(),
                    cfgmod.Mode(mode2 or "org"),
                    Path(output2).expanduser(),
                    force2,
                )
                svc.render_result(result)
