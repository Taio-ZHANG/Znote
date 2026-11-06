#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
WWW = os.path.join(ROOT, "www")
ATTACH = os.path.join(DATA, "attachments")
CONFIG = os.path.join(DATA, ".order.json")
PORT = int(os.environ.get("PORT", "8360"))
MAX_UPLOAD = 100 * 1024 * 1024

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def load_config():
    cfg = {"modules": [], "notes": {}, "sortMode": {}}
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    cfg.setdefault("modules", [])
    cfg.setdefault("notes", {})
    cfg.setdefault("sortMode", {})
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def rel_path(abs_path):
    return os.path.relpath(abs_path, DATA).replace(os.sep, "/")


def safe_join(base, rel):
    base = os.path.abspath(base)
    p = os.path.abspath(os.path.join(base, rel))
    if p != base and not p.startswith(base + os.sep):
        return None
    return p


def valid_module(name):
    if not name or len(name) > 100:
        return False
    if "/" in name or "\\" in name or name in (".", ".."):
        return False
    if name.startswith(".") or name != name.strip():
        return False
    return True


def sanitize_title(title):
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", title).strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        t = "未命名"
    return t[:120]


def unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{root}-{n}{ext}"):
        n += 1
    return f"{root}-{n}{ext}"


def list_modules():
    if not os.path.isdir(DATA):
        return []
    folders = {}
    for name in os.listdir(DATA):
        if name.startswith(".") or name == "attachments":
            continue
        folder = os.path.join(DATA, name)
        if not os.path.isdir(folder):
            continue
        count = 0
        for f in os.listdir(folder):
            if f.startswith("."):
                continue
            if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(".md"):
                count += 1
        folders[name] = count
    cfg = load_config()
    mode = cfg["sortMode"].get("modules", "manual")
    if mode == "name":
        names = sorted(folders)
    else:
        ordered = [m for m in cfg["modules"] if m in folders]
        names = ordered + sorted(m for m in folders if m not in cfg["modules"])
    return [{"name": n, "count": folders[n]} for n in names]


def list_notes(module):
    if not valid_module(module):
        return []
    folder = os.path.join(DATA, module)
    if not os.path.isdir(folder):
        return []
    notes = {}
    for f in os.listdir(folder):
        if f.startswith(".") or not f.lower().endswith(".md"):
            continue
        fp = os.path.join(folder, f)
        if os.path.isfile(fp):
            notes[f] = os.stat(fp).st_mtime
    cfg = load_config()
    mode = cfg["sortMode"].get("notes", "manual")
    known = cfg["notes"].get(module, [])
    if mode == "name":
        keys = sorted(notes)
    elif mode == "time":
        keys = sorted(notes, key=lambda f: notes[f], reverse=True)
    else:
        ordered = [f for f in known if f in notes]
        keys = ordered + sorted((f for f in notes if f not in known),
                                key=lambda f: notes[f], reverse=True)
    return [{"name": f, "path": rel_path(os.path.join(folder, f)), "mtime": notes[f]} for f in keys]


def search_notes(q):
    if not q:
        return []
    ql = q.lower()
    results = []
    for name in os.listdir(DATA):
        if name.startswith(".") or name == "attachments":
            continue
        folder = os.path.join(DATA, name)
        if not os.path.isdir(folder):
            continue
        for f in os.listdir(folder):
            if f.startswith(".") or not f.lower().endswith(".md"):
                continue
            fp = os.path.join(folder, f)
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            idx = text.lower().find(ql)
            if idx < 0:
                continue
            st = os.stat(fp)
            start = max(0, idx - 40)
            end = min(len(text), idx + 80)
            snippet = text[start:end].replace("\r", "").replace("\n", " ").strip()
            results.append({
                "name": f,
                "module": name,
                "path": rel_path(fp),
                "snippet": snippet,
                "mtime": st.st_mtime,
            })
    results.sort(key=lambda r: r["mtime"], reverse=True)
    return results[:200]


def write_note(module, title, content, path):
    """写入（或新建）一篇笔记，返回最终相对路径；API 与桌面壳共用。"""
    if path:
        target = safe_join(DATA, path)
        if target is None or not os.path.isfile(target) or not target.lower().endswith(".md"):
            raise FileNotFoundError(path)
        module = os.path.basename(os.path.dirname(target))
        old_name = os.path.basename(target)
        new_name = sanitize_title(title) + ".md"
        new_target = os.path.join(os.path.dirname(target), new_name)
        renamed = os.path.abspath(new_target).lower() != os.path.abspath(target).lower()
        if renamed:
            new_target = unique_path(new_target)
            os.rename(target, new_target)
            target = new_target
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        cfg = load_config()
        lst = cfg["notes"].setdefault(module, [])
        final = os.path.basename(target)
        if renamed:
            lst = [final if n == old_name else n for n in lst]
        elif final not in lst:
            lst.insert(0, final)
        cfg["notes"][module] = lst
        save_config(cfg)
        return rel_path(target)

    if not valid_module(module):
        raise ValueError("请先选择模块")
    folder = os.path.join(DATA, module)
    os.makedirs(folder, exist_ok=True)
    target = unique_path(os.path.join(folder, sanitize_title(title) + ".md"))
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    cfg = load_config()
    lst = cfg["notes"].setdefault(module, [])
    final = os.path.basename(target)
    if final not in lst:
        lst.insert(0, final)
    cfg["notes"][module] = lst
    save_config(cfg)
    return rel_path(target)


def parse_multipart(body, boundary):
    parts = {}
    delim = ("--" + boundary).encode("utf-8")
    for chunk in body.split(delim):
        if chunk in (b"", b"\r\n", b"--\r\n", b"--"):
            continue
        idx = chunk.find(b"\r\n\r\n")
        if idx < 0:
            continue
        headers = chunk[:idx].decode("utf-8", "replace")
        data = chunk[idx + 4:]
        if data.endswith(b"\r\n"):
            data = data[:-2]
        name = None
        filename = None
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-disposition"):
                m = re.search(r'name="([^"]*)"', line)
                if m:
                    name = m.group(1)
                m = re.search(r'filename="([^"]*)"', line)
                if m:
                    filename = m.group(1)
        if name:
            parts[name] = {"filename": filename, "data": data}
    return parts


class Handler(BaseHTTPRequestHandler):
    server_version = "Znote/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD" and body:
            try:
                self.wfile.write(body)
            except OSError:
                pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _err(self, msg, code=400):
        self._json({"error": msg}, code)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD + 1024 * 1024:
            return None
        return self.rfile.read(length)

    def _serve_static(self, base, rel, unquote=True):
        if unquote:
            rel = urllib.parse.unquote(rel)
        target = safe_join(base, rel)
        if target is None:
            self._err("非法路径", 403)
            return
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
            if not os.path.exists(target):
                self._err("禁止访问", 403)
                return
        if not os.path.isfile(target):
            self._err("Not Found", 404)
            return
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        try:
            with open(target, "rb") as f:
                data = f.read()
        except OSError:
            self._err("读取失败", 500)
            return
        self._send(200, data, ctype)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if route == "/api/modules":
            cfg = load_config()
            self._json({"modules": list_modules(), "sortMode": cfg["sortMode"].get("modules", "manual")})
            return

        if route == "/api/notes":
            module = qs.get("module", [""])[0]
            if not valid_module(module):
                self._err("模块名不合法")
                return
            cfg = load_config()
            self._json({"notes": list_notes(module), "sortMode": cfg["sortMode"].get("notes", "manual")})
            return

        if route == "/api/note":
            path = qs.get("path", [""])[0]
            target = safe_join(DATA, path)
            if target is None or not os.path.isfile(target) or not target.lower().endswith(".md"):
                self._err("笔记不存在", 404)
                return
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            self._json({"content": content})
            return

        if route == "/api/search":
            q = qs.get("q", [""])[0]
            self._json({"results": search_notes(q)})
            return

        if route.startswith("/files/"):
            self._serve_static(DATA, route[len("/files/"):])
            return

        if route == "/":
            self._serve_static(WWW, "index.html", unquote=False)
            return

        self._serve_static(WWW, route.lstrip("/"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/api/modules":
            try:
                payload = json.loads(self._read_body() or b"{}")
            except (ValueError, TypeError):
                self._err("请求格式错误")
                return
            name = (payload.get("name") or "").strip()
            if not valid_module(name):
                self._err("模块名不合法（不能包含 / \\ 等字符）")
                return
            folder = os.path.join(DATA, name)
            os.makedirs(folder, exist_ok=True)
            cfg = load_config()
            if name not in cfg["modules"]:
                cfg["modules"].append(name)
            save_config(cfg)
            self._json({"ok": True, "name": name})
            return

        if route == "/api/order":
            try:
                payload = json.loads(self._read_body() or b"{}")
            except (ValueError, TypeError):
                self._err("请求格式错误")
                return
            otype = payload.get("type")
            items = [str(i) for i in (payload.get("items") or [])]
            cfg = load_config()
            if otype == "modules":
                cfg["modules"] = items
                cfg["sortMode"]["modules"] = "manual"
            elif otype == "notes":
                module = (payload.get("module") or "").strip()
                if valid_module(module):
                    cfg["notes"][module] = items
                    cfg["sortMode"]["notes"] = "manual"
            save_config(cfg)
            self._json({"ok": True})
            return

        if route == "/api/sortmode":
            try:
                payload = json.loads(self._read_body() or b"{}")
            except (ValueError, TypeError):
                self._err("请求格式错误")
                return
            otype = payload.get("type")
            mode = payload.get("mode")
            if otype in ("modules", "notes") and mode in ("manual", "name", "time"):
                cfg = load_config()
                cfg["sortMode"][otype] = mode
                save_config(cfg)
                self._json({"ok": True})
                return
            self._err("参数错误")
            return

        if route == "/api/note":
            try:
                payload = json.loads(self._read_body() or b"{}")
            except (ValueError, TypeError):
                self._err("请求格式错误")
                return
            module = (payload.get("module") or "").strip()
            title = (payload.get("title") or "").strip()
            content = payload.get("content") or ""
            path = (payload.get("path") or "").strip()
            try:
                final_path = write_note(module, title, content, path)
            except FileNotFoundError:
                self._err("笔记不存在", 404)
                return
            except ValueError as e:
                self._err(str(e))
                return
            self._json({"ok": True, "path": final_path})
            return

        if route == "/api/upload":
            body = self._read_body()
            ctype = self.headers.get("Content-Type", "")
            m = re.search(r"boundary=([^;]+)", ctype)
            if body is None or not m:
                self._err("上传失败：文件过大或缺少 boundary")
                return
            parts = parse_multipart(body, m.group(1).strip().strip('"'))
            file_part = parts.get("file")
            if not file_part or not file_part.get("filename"):
                self._err("缺少文件")
                return
            data = file_part["data"]
            if len(data) > MAX_UPLOAD:
                self._err("文件超过 100MB")
                return
            fname = os.path.basename(file_part["filename"])
            safe = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", fname)
            safe = safe.strip("._")
            if not safe or "." not in safe:
                safe = "image.png"
            if len(safe) > 100:
                root, ext = os.path.splitext(safe)
                safe = root[:80] + ext
            os.makedirs(ATTACH, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(ATTACH, f"{stamp}_{safe}")
            path = unique_path(path)
            with open(path, "wb") as f:
                f.write(data)
            name = os.path.basename(path)
            self._json({"ok": True, "url": f"/files/attachments/{name}", "md": f"../attachments/{name}"})
            return

        if route == "/api/shutdown":
            self._json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        self._err("Not Found", 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if route.startswith("/api/modules/"):
            name = urllib.parse.unquote(route[len("/api/modules/"):])
            if not valid_module(name):
                self._err("模块名不合法")
                return
            folder = os.path.join(DATA, name)
            if not os.path.isdir(folder):
                self._err("模块不存在", 404)
                return
            shutil.rmtree(folder)
            cfg = load_config()
            cfg["modules"] = [m for m in cfg["modules"] if m != name]
            cfg["notes"].pop(name, None)
            save_config(cfg)
            self._json({"ok": True})
            return

        if route == "/api/note":
            path = qs.get("path", [""])[0]
            target = safe_join(DATA, path)
            if target is None or not os.path.isfile(target) or not target.lower().endswith(".md"):
                self._err("笔记不存在", 404)
                return
            module = os.path.basename(os.path.dirname(target))
            name = os.path.basename(target)
            os.remove(target)
            cfg = load_config()
            cfg["notes"].setdefault(module, [])
            cfg["notes"][module] = [n for n in cfg["notes"][module] if n != name]
            save_config(cfg)
            self._json({"ok": True})
            return

        self._err("Not Found", 404)


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(ATTACH, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Znote 服务已启动: http://127.0.0.1:{PORT}/")
    print(f"数据目录: {DATA}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
