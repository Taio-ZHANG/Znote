#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Znote 桌面壳：本地服务 + 原生窗口（WebView2），不再打开浏览器。

- 双击 start.bat（桌面 Znote 快捷方式）即弹出独立应用窗口；
- 点窗口右上角 × 或界面里的“退出”按钮，一次点击即退出；
- 退出前若编辑器里有未保存的内容，会静默写入 data 文件夹，不弹任何确认框。
"""
import os
import threading
import urllib.request

import webview

import server


def _server_alive():
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.PORT}/api/modules", timeout=1
        ) as r:
            return r.status == 200
    except Exception:
        return False


def _flush_dirty():
    """窗口销毁前，把编辑器里未保存的内容同步写盘（无弹窗、无确认）。"""
    w = webview.windows[0] if webview.windows else None
    if w is None:
        return
    try:
        snap = w.evaluate_js(
            "window.__znoteSnapshot ? window.__znoteSnapshot() : null"
        )
    except Exception:
        return
    if not snap or not isinstance(snap, dict):
        return
    try:
        server.write_note(
            (snap.get("module") or "").strip(),
            (snap.get("title") or "").strip(),
            snap.get("content") or "",
            (snap.get("path") or "").strip(),
        )
    except (FileNotFoundError, ValueError, OSError):
        pass


class Api:
    def quit_app(self):
        # 由前端“退出”按钮调用：先落盘未保存内容，再关窗口。
        _flush_dirty()
        for w in list(webview.windows):
            w.destroy()


def main():
    os.makedirs(server.DATA, exist_ok=True)
    os.makedirs(server.ATTACH, exist_ok=True)

    try:
        httpd = server.ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler)
    except OSError:
        # 端口被占：若已是 Znote 服务则直接复用（关闭窗口时不动它）；
        # 否则是别的程序占了 8360，提示后退出。
        if _server_alive():
            httpd = None
        else:
            webview.create_window(
                "Znote",
                html=f"<h2 style='font-family:sans-serif'>端口 {server.PORT} 已被其他程序占用，无法启动 Znote。</h2>",
                width=420,
                height=160,
            )
            webview.start()
            return
    else:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

    window = webview.create_window(
        "Znote",
        f"http://127.0.0.1:{server.PORT}/",
        js_api=Api(),
        width=1280,
        height=820,
        min_size=(960, 600),
        text_select=True,
    )
    try:
        webview.start()
    finally:
        _flush_dirty()
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    main()
