# Znote

本地 Markdown 笔记桌面应用，使用 Python 本地服务、pywebview 桌面窗口和离线前端资源。

A local Markdown notebook with module folders, search, attachments and a native desktop window.

## 功能

- 按模块组织笔记，Markdown 编辑与预览、搜索与排序。
- 支持附件和图片上传；笔记以普通 `.md` 文件保存。
- Ctrl+S 保存，Ctrl+N 新建，Ctrl+K 搜索，Ctrl+B 折叠侧栏，Ctrl+E 切换编辑/预览。
- 关闭窗口前尝试保存当前编辑内容。

## 安装与启动

本次公开版本针对 Windows 验证。需要 Python 3.10+ 和 Microsoft Edge WebView2 Runtime。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe znote_app.py
```

如果依赖已安装在默认 Python 中，可双击 `start.bat`。使用虚拟环境时请使用上面的明确路径启动。
调试本地服务可运行 `python server.py`，在浏览器访问 `http://127.0.0.1:8360`，退出调试服务按 Ctrl+C。

## 保存、隐私与边界

第一次启动会创建 `data/`；笔记、附件及 `.order.json` 都位于其中。备份时退出应用后复制整个 `data/`。
公开仓库不包含任何真实笔记、附件、账号密码、API 配置或原笔记文件名。
服务只绑定本机回环地址，默认端口 8360；可设置 `PORT` 环境变量更换端口。
这是个人本地应用，不提供多用户认证。不要把服务转发到公网，也不要把它作为共享笔记服务器部署。
Markdown 预览仅用于自己信任的内容；当前版本没有承诺对任意恶意 HTML 做完整净化。

## 开发检查

```powershell
python -m compileall -q server.py znote_app.py
node --check www/app.js
```

界面需在 Windows 上手动验证；发布整理另以临时目录验证了笔记写入、读取、重命名和搜索。
首次公开版本编号为 0.1.0，是 2026-11-06 当前本机源码的公开快照，不表示原应用此前已有该版本号。

## 许可

项目采用 [MIT](LICENSE)。内置 Marked 5.1.2 采用 MIT，完整许可位于 `www/vendor/marked-LICENSE.md`。
pywebview 等依赖遵守自己的上游许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
