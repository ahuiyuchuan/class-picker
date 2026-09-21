# @author ahui
# 固定工作目录并检查原生命令退出码，防止前端失败后误打包旧资源。
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    # 优先使用项目隔离环境，防止系统 Python 中的旧依赖被静默打进 EXE。
    $projectPython = Join-Path $root '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $projectPython)) {
        $projectPython = (Get-Command python -ErrorAction Stop).Source
    }
    $dependencyCheck = @'
import importlib.metadata as metadata
from pathlib import Path

for line in Path('requirements.txt').read_text(encoding='utf-8').splitlines():
    if not line.strip() or line.startswith('#'):
        continue
    name, expected = line.strip().split('==')
    actual = metadata.version(name)
    if actual != expected:
        raise RuntimeError(f'{name}: expected {expected}, installed {actual}')
'@
    & $projectPython -c $dependencyCheck
    if ($LASTEXITCODE -ne 0) { throw 'Install requirements.txt in the project environment before building.' }
    Push-Location frontend
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Vue build failed' }
    } finally { Pop-Location }
    & $projectPython -m PyInstaller --noconfirm --clean --onefile --windowed --name ClassPicker --icon packaging/ClassPicker.ico --add-data 'frontend/dist;frontend/dist' --add-data 'packaging/ClassPicker.ico;packaging' backend/main.py
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
} finally { Pop-Location }
