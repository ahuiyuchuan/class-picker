# 开发与验证指南

<!-- @author ahui -->

以下命令均在仓库根目录执行。

## 环境与启动

技术栈为 Python、Vue 3、SQLite、pywebview，使用系统 **Microsoft Edge WebView2 Runtime**。目标平台为 Windows；当前构建在 Python 3.14.6、Node.js 20.19.0 下验证。Python 依赖固定于 requirements 文件，前端依赖由 package-lock.json 锁定。

在仓库根目录使用 PowerShell：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run build
./.venv/Scripts/python.exe backend/main.py
```

桌面入口加载 `frontend/dist`，修改前端后需要重新构建。仅运行 Vite 无法完整验证 Python 数据桥接和 Windows 窗口行为。

## 单文件打包

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build_onefile.ps1
```

脚本优先使用项目 `.venv`，核对 Python 依赖版本，构建 Vue 后通过 PyInstaller 打包，产物为 `dist/ClassPicker.exe`。

程序代码、前端资源与图标包含在单个 EXE 中，但目标电脑仍需系统 WebView2 Runtime。运行数据写入用户目录，不写入 EXE。源码仓库不包含 EXE、依赖目录、数据库或临时测试产物；克隆后需按上面的步骤构建。

## 数据与兼容性

默认数据目录：`%LOCALAPPDATA%\ClassroomPicker\data`。可通过环境变量 `CLASS_PICKER_DATA_DIR` 指定独立目录，测试时必须与正式名单隔离。

当前数据库格式为 v2：启动时自动升级 v1，升级前生成 `pre-v2` 备份；恢复旧备份时先在临时副本升级和校验，再替换当前数据库。回退到不支持 v2 的旧程序须使用升级前备份，升级后新增修改不会存在于旧备份中。

写操作使用事务与参数绑定，抽取请求具有幂等保护。同一 Windows 会话、同一路径的新版本进程通过命名互斥协调写入、快照及备份恢复；旧版本、外部 SQLite 工具与其他 Windows 会话不遵循该锁，恢复前应关闭这些访问者。

## 验证

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test*.py'
./.venv/Scripts/python.exe -m ruff check backend tests --select F,E9
./.venv/Scripts/python.exe -m compileall -q backend tests
npm --prefix frontend run build
./.venv/Scripts/python.exe tests/verify_audit.py
./.venv/Scripts/python.exe tests/verify_draw_counts.py
./.venv/Scripts/python.exe tests/verify_roster_about.py
./.venv/Scripts/python.exe tests/verify_window_transitions.py
./.venv/Scripts/python.exe tests/verify_fullscreen_pages.py
```

GUI 专项脚本会打开真实 WebView2 窗口，在仓库父目录创建独立测试数据、截图和 JSON 报告。需要交互式 Windows 桌面，报告中的 `passed` 应为 `true`。

综合窗口检查可使用源码入口或打包 EXE 的 `--verify-window` 参数，必须先设置两个环境变量：

```powershell
$testRoot = Join-Path $env:TEMP ('class-picker-check-' + [guid]::NewGuid().ToString('N'))
$env:CLASS_PICKER_DATA_DIR = Join-Path $testRoot 'data'
$env:CLASS_PICKER_TEST_REPORT = Join-Path $testRoot 'report.json'
./.venv/Scripts/python.exe backend/main.py --verify-window
Get-Content -Raw -Encoding UTF8 $env:CLASS_PICKER_TEST_REPORT
Remove-Item Env:CLASS_PICKER_DATA_DIR, Env:CLASS_PICKER_TEST_REPORT
```

测试覆盖数据库事务、导入边界、抽取状态、名单维护、窗口切换及全屏页面布局。尚未覆盖跨显卡、多显示器混合 DPI 的逐帧验证；未配置独立前端 lint/类型检查，采用 Vue 构建和真实窗口回归。

安装时 `lucide-vue-next@1.0.0` 会提示已弃用，当前仍可正常构建；保留锁定依赖，后续迁移到 `@lucide/vue` 时需同步验证图标导入及页面显示。

## 目录与维护资料

| 目录 | 职责 |
| --- | --- |
| `backend/` | 桌面入口、数据桥接、SQLite、进程互斥与窗口过渡 |
| `frontend/src/` | 课堂及管理页面、公共组件、交互状态和样式 |
| `frontend/public/` | 前端静态图标 |
| `packaging/` | Windows 图标与单文件构建脚本 |
| `tests/` | 数据单元测试及真实桌面回归 |
| `docs/` | 业务规则、数据接口及维护说明 |

[实现与维护说明](implementation.md) 介绍接口参数、空值语义、导入边界、事务与迁移细节。测试数据、截图和报告不随仓库提交，使用当前脚本可生成检查结果。

作者：ahui。采用 [Apache License 2.0](../LICENSE)。
