from pathlib import Path

import streamlit as st

import services as svc
from gitteam import config as cfgmod
from gitteam import conventions as conv
from gitteam.commands import ops as ops_cmd
from gitteam.errors import ConventionError

cfg, _ = svc.load_config()
rules = (cfg or cfgmod.default_config()).conventions
default_branch = (cfg or cfgmod.default_config()).repo.default_branch
global_dry = svc.dry_run_notice()

st.text_input(
    "ローカルリポジトリのパス",
    value=str(Path.cwd()),
    key="ops_repo_path",
    persist_state="session",
    help="ブランチ作成・コミット検証・PR・リリース・hooks はこのリポジトリに対して実行します。",
)
repo_path = Path(st.session_state.ops_repo_path).expanduser()
repo_info = svc.local_repo_info(repo_path)
if repo_info["is_repo"]:
    st.caption(
        f":material/check: {repo_info['toplevel']} - ブランチ **{repo_info['branch']}** - origin: {repo_info['remote'] or '(なし)'}"
    )
else:
    st.caption(":material/warning: git リポジトリではありません。純粋な検証（名前・メッセージ）のみ利用できます。")
has_repo = bool(repo_info["is_repo"])

branch_tab, commit_tab, pr_tab, hooks_tab = st.tabs(["ブランチ", "コミット", "PR・リリース", "git hooks"])

with branch_tab:
    st.markdown(f"命名規則: `{rules.branch_pattern}`")
    cols = st.columns([1, 2, 1])
    btype = cols[0].selectbox("種別", rules.branch_types)
    desc = cols[1].text_input("説明（自動でスラッグ化）", placeholder="add login page")
    issue = cols[2].number_input("Issue 番号", min_value=0, step=1, value=0)
    generated = None
    if desc.strip():
        try:
            generated = conv.build_branch_name(rules, btype, desc, int(issue) or None)
            st.success(f"生成されるブランチ名: `{generated}`", icon=":material/check_circle:")
        except ConventionError as exc:
            st.error(str(exc))
    if st.button("このブランチを作成して切り替え", icon=":material/alt_route:", disabled=not (generated and has_repo)):
        st.session_state.ops_branch_result = svc.run_captured(
            ops_cmd.branch_new, svc.make_context(), btype, desc, int(issue) or None, None, cwd=repo_path
        )
    svc.render_result(st.session_state.get("ops_branch_result"), empty_hint="")

    st.markdown("**任意のブランチ名を検証**")
    check_name = st.text_input("ブランチ名", placeholder="feature/42-add-login-page", label_visibility="collapsed")
    if check_name:
        problems = conv.validate_branch_name(rules, check_name)
        if problems:
            for p in problems:
                st.error(p)
        else:
            st.success("規約に適合しています", icon=":material/check:")

with commit_tab:
    st.markdown(f"Conventional Commits: `<type>(<scope>)?: <description>`  種別: {', '.join(rules.commit_types)}")
    message = st.text_area("コミットメッセージを検証", placeholder="feat(auth): add login page", height=120)
    if message.strip():
        problems = conv.validate_commit_message(rules, message)
        if problems:
            for p in problems:
                st.error(p)
        else:
            st.success("規約に適合しています", icon=":material/check:")
    st.markdown("**リビジョン範囲を検証**")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        rev_range = st.text_input("範囲", value=f"origin/{default_branch}..HEAD")
        if st.button("検証", icon=":material/rule:", disabled=not has_repo):
            st.session_state.ops_commit_result = svc.run_captured(
                ops_cmd.commit_check, svc.make_context(dry_run=True), rev_range, None, None, cwd=repo_path
            )
    svc.render_result(st.session_state.get("ops_commit_result"), empty_hint="")

with pr_tab:
    st.markdown("**プルリクエストを作成**")
    st.caption("現在のブランチをプッシュし、テンプレート・ラベル・レビュアーを設定して PR を開きます。")
    with st.form("ops_pr"):
        pr_title = st.text_input("タイトル（空欄で自動生成）")
        pr_base = st.text_input("ベースブランチ", value=default_branch)
        with st.container(horizontal=True):
            pr_draft = st.toggle("ドラフト", value=False)
            pr_no_verify = st.toggle("規約チェックをスキップ", value=False)
        pr_reviewers = st.text_input("追加レビュアー（カンマ区切り）")
        pr_labels = st.text_input("追加ラベル（カンマ区切り）")
        pr_clicked = st.form_submit_button("PR を作成", type="primary", icon=":material/merge:", disabled=not has_repo)
    if pr_clicked:
        st.session_state.ops_pr_result = svc.run_captured(
            ops_cmd.pr_create,
            svc.make_context(),
            title=pr_title.strip() or None,
            base=pr_base.strip() or None,
            draft=pr_draft,
            reviewers=[r.strip() for r in pr_reviewers.split(",") if r.strip()],
            labels=[label.strip() for label in pr_labels.split(",") if label.strip()],
            no_verify=pr_no_verify,
            cwd=repo_path,
        )
    svc.render_result(st.session_state.get("ops_pr_result"), empty_hint="")

    st.markdown("**リリース**")
    st.caption(f"`{default_branch}` 上でタグ `{rules.tag_prefix}X.Y.Z` を作成し、GitHub Release をリリースノート付きで公開します。")
    with st.form("ops_release"):
        version = st.text_input("バージョン", placeholder="1.4.0")
        with st.container(horizontal=True):
            prerelease = st.toggle("プレリリース", value=False)
            release_draft = st.toggle("ドラフト", value=False, key="release_draft")
            allow_dirty = st.toggle("未コミット変更を許容", value=False)
        release_clicked = st.form_submit_button("リリース", type="primary", icon=":material/new_releases:", disabled=not has_repo)
    if release_clicked:
        if not version.strip():
            st.error("バージョンを入力してください。")
        else:
            st.session_state.ops_release_result = svc.run_captured(
                ops_cmd.release,
                svc.make_context(),
                version.strip(),
                prerelease=prerelease,
                draft=release_draft,
                allow_dirty=allow_dirty,
                cwd=repo_path,
            )
    svc.render_result(st.session_state.get("ops_release_result"), empty_hint="")

with hooks_tab:
    st.caption("commit-msg / pre-push フックを導入し、コミット時と push 時に規約を検証します。")
    mode = st.segmented_control(
        "配置先",
        ["shared", "local"],
        format_func=lambda v: ".githooks（リポジトリで共有）" if v == "shared" else ".git/hooks（この clone のみ）",
        default="shared",
    )
    if st.button("hooks を導入", icon=":material/webhook:", type="primary", disabled=not has_repo):
        st.session_state.ops_hooks_result = svc.run_captured(
            ops_cmd.hooks_install, svc.make_context(), mode == "shared", cwd=repo_path
        )
    svc.render_result(st.session_state.get("ops_hooks_result"), empty_hint="")
