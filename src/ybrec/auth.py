"""Obtain Yuanbao login credentials.

Two sources, tried in order:
1. Environment variables YBREC_X_ID / YBREC_X_TOKEN (any platform).
2. A running Yuanbao desktop app (Windows, WebView2) started with a
   remote-debugging port; credentials are read from the page's localStorage
   through the Chrome DevTools Protocol. The app keeps the token fresh itself.
"""
from __future__ import annotations

import itertools
import json
import os
import platform
import subprocess
import time
import urllib.request

# localStorage keys the desktop app sends as request headers.
HEADER_KEYS = ["X-ID", "X-Token", "X-Instance-Id", "X-AppVersion", "X-Channel", "X-A3"]
DEFAULT_PORT = 9229
DEFAULT_EXE = r"C:\Program Files\Tencent\Yuanbao\yuanbao.exe"
PAGE_ORIGINS = ("https://tencent.yuanbao/", "https://yuanbao.tencent.com/")


class AuthError(RuntimeError):
    pass


def _no_proxy_open(url: str, timeout: float = 3):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url, timeout=timeout)


def from_env() -> dict | None:
    xid, tok = os.environ.get("YBREC_X_ID"), os.environ.get("YBREC_X_TOKEN")
    if xid and tok:
        return {"X-ID": xid, "X-Token": tok}
    return None


def _debug_targets(port: int) -> list[dict]:
    try:
        with _no_proxy_open(f"http://127.0.0.1:{port}/json") as r:
            return json.load(r)
    except OSError as e:
        raise AuthError(
            f"无法连接元宝桌面版调试端口 127.0.0.1:{port}（{e}）。"
            "请先运行 `ybrec desktop` 以调试模式启动元宝桌面版并登录。"
        ) from None


def from_desktop(port: int = DEFAULT_PORT) -> dict:
    import websocket  # websocket-client

    pages = [t for t in _debug_targets(port)
             if t.get("type") == "page" and t.get("url", "").startswith(PAGE_ORIGINS)]
    if not pages:
        raise AuthError("调试端口上没有找到元宝页面，请确认元宝桌面版已打开。")
    # Prefer the main chat window; any page of the same origin shares localStorage.
    pages.sort(key=lambda t: "/chat" not in t["url"])
    ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"],
                                     suppress_origin=True, timeout=15,
                                     http_proxy_host=None)
    try:
        expr = "JSON.stringify(Object.fromEntries(%s.map(k=>[k,localStorage.getItem(k)])))" % json.dumps(HEADER_KEYS)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "returnByValue": True}}))
        for _ in itertools.count():
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                break
    finally:
        ws.close()
    value = msg.get("result", {}).get("result", {}).get("value")
    if not value:
        raise AuthError(f"读取 localStorage 失败：{msg}")
    creds = {k: v for k, v in json.loads(value).items() if v}
    if not (creds.get("X-ID") and creds.get("X-Token")):
        raise AuthError("元宝桌面版未登录（localStorage 里没有 X-ID / X-Token）。请先在元宝里登录。")
    return creds


def get_credentials(port: int = DEFAULT_PORT) -> dict:
    return from_env() or from_desktop(port)


# ---------------------------------------------------------------- desktop launch

def _is_wsl() -> bool:
    try:
        return "microsoft" in open("/proc/version").read().lower()
    except OSError:
        return False


def launch_desktop(port: int = DEFAULT_PORT, exe: str = DEFAULT_EXE, wait: float = 40) -> None:
    """Restart the Yuanbao desktop app with a WebView2 remote-debugging port."""
    args = f"--remote-debugging-port={port}"
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/F", "/IM", "yuanbao.exe"], capture_output=True)
        time.sleep(2)
        env = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=args)
        subprocess.Popen([exe], env=env, creationflags=0x00000008)  # DETACHED_PROCESS
    elif _is_wsl():
        ps = (
            "Stop-Process -Name yuanbao -Force -ErrorAction SilentlyContinue; Start-Sleep 2; "
            f"$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='{args}'; "
            f"Start-Process '{exe}'"
        )
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
    else:
        raise AuthError("`ybrec desktop` 只支持 Windows / WSL。其他平台请用环境变量 YBREC_X_ID / YBREC_X_TOKEN。")

    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            if any(t.get("url", "").startswith(PAGE_ORIGINS) for t in _debug_targets(port)):
                return
        except AuthError:
            pass
        time.sleep(1)
    raise AuthError(
        f"元宝已重启，但 {wait:.0f}s 内没连上调试端口 {port}。"
        "WSL 下需要 mirrored 网络模式（.wslconfig: networkingMode=mirrored）。"
    )
