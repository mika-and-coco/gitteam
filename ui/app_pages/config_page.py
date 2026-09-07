from pathlib import Path

import pandas as pd
import streamlit as st

import glossary as gl
import services as svc
from gitteam.config import PERMISSIONS

st.caption("チームの決めごと（誰が・どのリポジトリに・どんなルールで）をここで編集します。変更は「保存する」を押すまで反映されません。")

path = svc.config_path()
cfg, cfg_error = svc.load_config()

location_problem = svc.check_config_path(path)
if location_problem:
    st.error(location_problem, icon=":material/error:")
    st.stop()
if not path.is_file():
    st.info("設定ファイルがまだありません。「はじめに」ページの手順 2 から作成してください。", icon=":material/info:")
    st.page_link("app_pages/start.py", label="はじめにページへ", icon=":material/flag:")
    st.stop()
if svc.trust_status(path) == "untrusted":
    st.warning(cfg_error, icon=":material/gpp_maybe:")
    st.stop()

if cfg is None:
    st.error(cfg_error, icon=":material/error:")
    st.caption("「詳細（YAML を直接編集）」タブで内容を修正して保存すると直ります。")

simple_tab, yaml_tab = st.tabs(["かんたん設定", "詳細（YAML を直接編集）"])

# ---------------------------------------------------------------- simple form
with simple_tab:
    if cfg is None:
        st.caption("設定ファイルにエラーがあるため、かんたん設定は使えません。")
    else:
        is_org = cfg.mode.is_org
        with st.form("simple_config"):
            st.markdown("##### 基本")
            owner = st.text_input("オーナー（GitHub のアカウント名）", value=cfg.owner, help=gl.help_text("owner"))
            mode_value = st.segmented_control(
                "利用形態",
                list(gl.MODE_LABELS),
                format_func=gl.MODE_LABELS.get,
                default=cfg.mode.value,
                help=gl.help_text("mode"),
            )
            visibility = st.segmented_control(
                "新しく作るリポジトリの公開範囲",
                list(gl.VISIBILITY_LABELS),
                format_func=gl.VISIBILITY_LABELS.get,
                default=cfg.repo.visibility,
                help=gl.help_text("visibility"),
            )

            teams_df = None
            collabs_df = None
            if is_org:
                st.markdown("##### チームとメンバー")
                st.caption(
                    "行を追加してチームを作り、メンバー欄に GitHub のユーザー名をカンマ区切りで入力します。"
                    "メンテナーはそのチームの設定を変更できる人です。",
                    help=gl.help_text("permission"),
                )
                teams_df = st.data_editor(
                    pd.DataFrame(
                        [
                            {
                                "チーム名": t.name,
                                "権限": t.permission,
                                "メンバー": ", ".join(t.members),
                                "メンテナー": ", ".join(t.maintainers),
                                "説明": t.description,
                            }
                            for t in cfg.teams
                        ],
                        columns=["チーム名", "権限", "メンバー", "メンテナー", "説明"],
                    ),
                    num_rows="dynamic",
                    hide_index=True,
                    column_config={
                        "チーム名": st.column_config.TextColumn(required=True),
                        "権限": st.column_config.SelectboxColumn(options=list(PERMISSIONS), required=True, help=gl.explain("permission")),
                        "メンバー": st.column_config.TextColumn(help="GitHub ユーザー名をカンマ区切りで"),
                        "メンテナー": st.column_config.TextColumn(help="チームの管理者。カンマ区切りで"),
                    },
                    key="teams_editor",
                )
            else:
                st.markdown("##### 共同作業者（コラボレーター）")
                st.caption(
                    "リポジトリに招待する人の GitHub ユーザー名と権限です。一人で使う場合は空のままで構いません。",
                    help=gl.help_text("collaborator"),
                )
                collabs_df = st.data_editor(
                    pd.DataFrame(
                        [{"ユーザー名": c.user, "権限": c.permission} for c in cfg.collaborators],
                        columns=["ユーザー名", "権限"],
                    ),
                    num_rows="dynamic",
                    hide_index=True,
                    column_config={
                        "ユーザー名": st.column_config.TextColumn(required=True),
                        "権限": st.column_config.SelectboxColumn(options=list(PERMISSIONS), required=True, help=gl.explain("permission")),
                    },
                    key="collabs_editor",
                )

            st.markdown("##### main ブランチの守り方")
            st.caption(
                "main への変更はプルリクエスト経由に限定し、以下の条件を満たさないとマージできないようにします。",
                help=gl.help_text("branch_protection"),
            )
            pc1, pc2, pc3 = st.columns(3)
            approvals = pc1.number_input("必要な承認レビュー数", min_value=0, max_value=6, value=cfg.protection.required_approvals)
            codeowner_review = pc2.toggle(
                "担当者（CODEOWNERS）のレビューを必須にする",
                value=cfg.protection.require_code_owner_reviews,
                help=gl.help_text("codeowners"),
            )
            enforce_admins = pc3.toggle(
                "管理者にもルールを適用する",
                value=cfg.protection.enforce_admins,
                help="OFF にすると管理者はルールを無視してマージできます。",
            )

            st.markdown("##### 作業ルール")
            rc1, rc2, rc3 = st.columns(3)
            subject_max = rc1.number_input(
                "コミット件名の最大文字数",
                min_value=20,
                max_value=max(200, cfg.conventions.commit_subject_max),
                value=cfg.conventions.commit_subject_max,
                help=gl.help_text("conventional_commits"),
            )
            require_issue = rc2.toggle(
                "ブランチ名に Issue 番号を必須にする",
                value=cfg.conventions.require_issue_in_branch,
                help=gl.help_text("branch_naming"),
            )
            tag_prefix = rc3.text_input("バージョンタグの接頭辞", value=cfg.conventions.tag_prefix, help="v にすると v1.2.0 のようなタグになります。")

            st.markdown("##### PC のセットアップで自動的にクローンするリポジトリ")
            repos_text = st.text_area(
                "リポジトリ名（1 行に 1 つ）",
                value="\n".join(cfg.dev.repos),
                height=100,
                label_visibility="collapsed",
                placeholder="my-service\nmy-web",
            )

            saved = st.form_submit_button("保存する", type="primary", icon=":material/save:")

        if saved:

            def cell(value: object) -> str:
                if value is None or (isinstance(value, float) and value != value):  # NaN from data_editor
                    return ""
                return str(value).strip()

            def split_names(text: object) -> list[str]:
                return [x.strip() for x in cell(text).split(",") if x.strip()]

            teams = None
            collaborators = None
            if teams_df is not None:
                teams = [
                    {
                        "name": cell(row["チーム名"]),
                        "description": cell(row.get("説明")),
                        "permission": cell(row["権限"]) or "push",
                        "members": split_names(row.get("メンバー")),
                        "maintainers": split_names(row.get("メンテナー")),
                        "repos": ["*"],
                    }
                    for _, row in teams_df.iterrows()
                    if cell(row.get("チーム名"))
                ]
            if collabs_df is not None:
                collaborators = [
                    {"user": cell(row["ユーザー名"]), "permission": cell(row["権限"]) or "push", "repos": ["*"]}
                    for _, row in collabs_df.iterrows()
                    if cell(row.get("ユーザー名"))
                ]
            error = svc.save_simple_settings(
                path,
                {
                    "owner": owner.strip(),
                    "mode": mode_value or cfg.mode.value,
                    "visibility": visibility or cfg.repo.visibility,
                    "teams": teams,
                    "collaborators": collaborators,
                    "protection": {
                        "required_approvals": int(approvals),
                        "require_code_owner_reviews": bool(codeowner_review),
                        "enforce_admins": bool(enforce_admins),
                    },
                    "conventions": {
                        "commit_subject_max": int(subject_max),
                        "require_issue_in_branch": bool(require_issue),
                        "tag_prefix": tag_prefix.strip(),
                    },
                    "dev_repos": [line.strip() for line in repos_text.splitlines() if line.strip()],
                },
            )
            if error:
                st.error(error, icon=":material/error:")
            else:
                svc.reset_config_editor()
                st.toast("保存しました", icon=":material/save:")
                st.rerun()

        st.caption("利用形態を変更して保存すると、チーム / 共同作業者の欄が切り替わります。")

# ---------------------------------------------------------------- YAML editor
with yaml_tab:
    st.caption(f"設定ファイルそのものを編集します。場所: `{path}`。すべての項目にコメントで説明が付いています。")

    def _reload_editor() -> None:
        st.session_state.pop("config_editor", None)

    file_text, read_error = svc.readable_config_text(path)
    if file_text is None:
        st.error(read_error, icon=":material/error:")
        st.stop()
    if read_error:
        st.warning(read_error, icon=":material/warning:")
    st.text_area("gitteam.yaml", value=file_text, key="config_editor", height=520, label_visibility="collapsed")
    editor_text = st.session_state.get("config_editor", file_text)
    with st.container(horizontal=True):
        validate_clicked = st.button("チェックする", icon=":material/rule:", key="yaml_check")
        save_clicked = st.button("保存する", icon=":material/save:", type="primary", key="yaml_save")
        st.button("ファイルから読み直す", icon=":material/refresh:", on_click=_reload_editor)
    if validate_clicked or save_clicked:
        parsed, error = svc.validate_yaml_text(editor_text)
        if error:
            st.error(error, icon=":material/error:")
        else:
            st.success(
                f"問題ありません（オーナー: {parsed.owner} / 利用形態: {gl.MODE_LABELS[parsed.mode.value]}）",
                icon=":material/check_circle:",
            )
            if save_clicked:
                path.write_text(editor_text, encoding="utf-8", newline="\n")
                svc.reset_config_editor()
                st.toast("保存しました", icon=":material/save:")
                st.rerun()
    if cfg:
        with st.expander("既定値を含めた最終的な設定を見る", icon=":material/visibility:"):
            st.code(svc.effective_yaml(cfg), language="yaml")
        with st.expander("ラベル一覧（リポジトリに作成されるもの）", icon=":material/label:"):
            st.dataframe(
                [{"ラベル": label.name, "色": f"#{label.color}", "説明": label.description} for label in cfg.labels],
                hide_index=True,
            )
