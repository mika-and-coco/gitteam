from pathlib import Path

import streamlit as st

import glossary as gl
import services as svc
from gitteam import config as cfgmod
from gitteam import conventions as conv
from gitteam.commands import ops as ops_cmd
from gitteam.errors import ConventionError

st.caption("開発中に毎日行う作業（ブランチを切る、コミットメッセージを確かめる、プルリクエストを出す、リリースする）をルールどおりに行うためのページです。")

cfg, _ = svc.load_config()
rules = (cfg or cfgmod.default_config()).conventions
default_branch = (cfg or cfgmod.default_config()).repo.default_branch

st.text_input(
    "作業しているリポジトリの場所（PC 上のフォルダー）",
    value=str(Path.cwd()),
    key="ops_repo_path",
    persist_state="session",
    help="ブランチ作成・コミットの確認・PR・リリース・hooks は、このフォルダーのリポジトリに対して行います。",
)
repo_path = Path(st.session_state.ops_repo_path).expanduser()
repo_info = svc.local_repo_info(repo_path)
if repo_info["is_repo"]:
    st.caption(f":material/check: {repo_info['toplevel']} - 今いるブランチ **{repo_info['branch']}** - GitHub: {repo_info['remote'] or '(未設定)'}")
else:
    st.caption(":material/warning: このフォルダーは git リポジトリではありません。名前やメッセージの確認だけ利用できます。")
has_repo = bool(repo_info["is_repo"])

branch_tab, commit_tab, pr_tab, hooks_tab = st.tabs(["ブランチを切る", "コミットメッセージ", "PR とリリース", "自動チェック（hooks）"])

with branch_tab:
    st.caption("作業内容を入力すると、チームの命名規則に合ったブランチ名を自動で作ります。", help=gl.help_text("branch_naming"))
    cols = st.columns([1, 2, 1])
    btype = cols[0].selectbox("作業の種類", rules.branch_types, help="feature=新機能、fix=バグ修正、hotfix=緊急修正、chore=雑務、docs=文書、refactor=整理、test=テスト、release=リリース準備")
    desc = cols[1].text_input("作業内容（日本語可。英数字に変換されます）", placeholder="例: add login page")
    issue = cols[2].number_input("Issue 番号（任意）", min_value=0, step=1, value=0)
    generated = None
    if desc.strip():
        try:
            generated = conv.build_branch_name(rules, btype, desc, int(issue) or None)
            st.success(f"ブランチ名: `{generated}`", icon=":material/check_circle:")
        except ConventionError as exc:
            st.error(svc.friendly_error(str(exc)) or str(exc))
    if st.button("内容を確認する", icon=":material/visibility:", disabled=not (generated and has_repo), key="branch_confirm"):
        svc.stage_action("ops_branch", ops_cmd.branch_new, btype, desc, int(issue) or None, None, cwd=repo_path)
    svc.render_action("ops_branch", execute_label="このブランチを作成して切り替える")

    with st.expander("手で付けたブランチ名を確認する", icon=":material/rule:"):
        check_name = st.text_input("ブランチ名", placeholder="feature/42-add-login-page", label_visibility="collapsed")
        if check_name:
            problems = conv.validate_branch_name(rules, check_name)
            if problems:
                st.error("命名規則に合っていません: " + "; ".join(problems))
            else:
                st.success("命名規則に合っています", icon=":material/check:")

with commit_tab:
    st.caption(
        f"コミットメッセージは「種類: 説明」の形で書きます（例: `feat: ログイン画面を追加`）。種類: {', '.join(rules.commit_types)}",
        help=gl.help_text("conventional_commits"),
    )
    message = st.text_area("メッセージを入力して確認", placeholder="feat(auth): add login page", height=100)
    if message.strip():
        problems = conv.validate_commit_message(rules, message)
        if problems:
            for p in problems:
                st.error(p)
        else:
            st.success("規約に合っています", icon=":material/check:")
    st.markdown("**プッシュ前に、まだ送っていないコミットをまとめて確認する**")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        rev_range = st.text_input("確認する範囲", value=f"origin/{default_branch}..HEAD", help="通常は変更不要です。main に取り込まれていないコミットが対象になります。")
        if st.button("確認する", icon=":material/rule:", disabled=not has_repo):
            svc.run_direct("ops_commit", ops_cmd.commit_check, rev_range, None, None, cwd=repo_path)
    svc.render_direct("ops_commit")

with pr_tab:
    st.markdown("**プルリクエストを出す**")
    st.caption("今いるブランチを GitHub に送り、テンプレート・ラベル・レビュアーを設定してプルリクエストを作ります。", help=gl.help_text("pr"))
    with st.form("ops_pr"):
        pr_title = st.text_input("タイトル（空欄なら自動で付けます）")
        with st.expander("詳しい設定", icon=":material/tune:"):
            pr_base = st.text_input("取り込み先のブランチ", value=default_branch)
            with st.container(horizontal=True):
                pr_draft = st.toggle("下書き（ドラフト）として作る", value=False)
                pr_no_verify = st.toggle("規約のチェックを省略する", value=False)
            pr_reviewers = st.text_input("追加のレビュアー（カンマ区切り）")
            pr_labels = st.text_input("追加のラベル（カンマ区切り）")
        pr_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:", disabled=not has_repo)
    if pr_submitted:
        svc.stage_action(
            "ops_pr",
            ops_cmd.pr_create,
            title=pr_title.strip() or None,
            base=pr_base.strip() or None,
            draft=pr_draft,
            reviewers=[r.strip() for r in pr_reviewers.split(",") if r.strip()],
            labels=[label.strip() for label in pr_labels.split(",") if label.strip()],
            no_verify=pr_no_verify,
            cwd=repo_path,
        )
    svc.render_action("ops_pr", execute_label="プルリクエストを作成する")

    st.markdown("**リリースする**")
    st.caption(f"`{default_branch}` の今の状態にバージョンタグ（{rules.tag_prefix}1.2.0 など）を付け、変更点をまとめた GitHub Release を公開します。", help=gl.help_text("release"))
    with st.form("ops_release"):
        version = st.text_input("バージョン", placeholder="例: 1.4.0")
        with st.container(horizontal=True):
            prerelease = st.toggle("プレリリース（試験版）", value=False)
            release_draft = st.toggle("下書きとして作る", value=False, key="release_draft")
            allow_dirty = st.toggle("未コミットの変更があっても続ける", value=False)
        release_submitted = st.form_submit_button("内容を確認する", type="primary", icon=":material/visibility:", disabled=not has_repo)
    if release_submitted:
        if not version.strip():
            st.error("バージョンを入力してください。")
        else:
            svc.stage_action(
                "ops_release",
                ops_cmd.release,
                version.strip(),
                prerelease=prerelease,
                draft=release_draft,
                allow_dirty=allow_dirty,
                cwd=repo_path,
            )
    svc.render_action("ops_release", execute_label="リリースを公開する")

with hooks_tab:
    st.caption("コミットや push の直前に自動で走るチェックを、このリポジトリに入れます。規約に合わないコミットはその場で止まります。", help=gl.help_text("hooks"))
    mode = st.segmented_control(
        "入れる場所",
        ["shared", "local"],
        format_func=lambda v: "リポジトリに入れてチーム全員で共有（推奨）" if v == "shared" else "自分の PC のこのクローンだけ",
        default="shared",
    )
    if st.button("内容を確認する", icon=":material/visibility:", disabled=not has_repo, key="hooks_confirm"):
        svc.stage_action("ops_hooks", ops_cmd.hooks_install, (mode or "shared") == "shared", cwd=repo_path)
    svc.render_action("ops_hooks", execute_label="自動チェックを入れる")
