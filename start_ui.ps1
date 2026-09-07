# gitteam Web UI 起動スクリプト（PowerShell）
# 右クリック →「PowerShell で実行」、またはターミナルで .\start_ui.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[gitteam] 初回セットアップ: Python 仮想環境を作成し、依存パッケージをインストールします..."
    python -m venv .venv
    & $python -m pip install --quiet --upgrade pip
    & $python -m pip install --quiet -e ".[ui]"
}

Write-Host "[gitteam] 画面を起動します。ブラウザが開かない場合は http://localhost:8501 を開いてください。"
& $python -m streamlit run ui\streamlit_app.py --server.address localhost
