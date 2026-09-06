import streamlit as st

import glossary as gl

st.caption("画面に出てくる言葉の意味と、よくある疑問への答えです。")

query = st.text_input("用語を検索", placeholder="例: ブランチ、権限、PR", label_visibility="collapsed")
rows = gl.rows()
if query.strip():
    needle = query.strip().lower()
    rows = [r for r in rows if needle in r["用語"].lower() or needle in r["意味"].lower()]
if not rows:
    st.caption("該当する用語がありません。")
for row in rows:
    with st.container(border=True):
        st.markdown(f"**{row['用語']}**")
        st.markdown(row["意味"])

st.subheader("よくある質問", icon=":material/quiz:")
faqs = [
    (
        "何も変更せずに、どんな操作が行われるか確認だけしたい",
        "どのページでも「内容を確認する」ボタンを押すだけなら何も変更されません。"
        "確認結果の「これから行う操作」を見てから、「この内容で実行する」を押したときだけ GitHub やローカルに反映されます。",
    ),
    (
        "間違って実行してしまった",
        "ほとんどの操作は「設定どおりに揃える」処理なので、設定を直してもう一度実行すれば上書きされます。"
        "リポジトリの作成やメンバーの招待は GitHub 上で取り消してください（リポジトリの削除はこのアプリからは行いません）。",
    ),
    (
        "「権限が足りません」と表示される",
        "組織のチームを操作するには組織のオーナー権限と、gh の追加権限が必要です。"
        "ターミナルで `gh auth refresh -s admin:org` を実行してから再試行してください。",
    ),
    (
        "非公開リポジトリでブランチ保護がスキップされる",
        "GitHub の無料プランでは非公開リポジトリにブランチ保護を設定できません。"
        "リポジトリを公開にするか、有料プラン（個人は Pro、組織は Team 以上）にすると使えます。",
    ),
    (
        "設定ファイル（gitteam.yaml）はどこにある？",
        "サイドバーの「上級者向け」に場所が表示されます。「チームの設定」ページの「かんたん設定」タブで編集でき、"
        "YAML を直接書く必要はありません。",
    ),
    (
        "他のメンバーはどうやって同じルールを使う？",
        "設定ファイルをチームで共有し、各メンバーが「PC のセットアップ」を実行します。"
        "リポジトリに入れた git hooks と GitHub Actions が、アプリを使わなくてもルール違反を止めます。",
    ),
]
for question, answer in faqs:
    with st.expander(question, icon=":material/help_outline:"):
        st.markdown(answer)
