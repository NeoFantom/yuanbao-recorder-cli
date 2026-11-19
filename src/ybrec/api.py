"""Thin client for Yuanbao's (private, undocumented) voice-recorder web API."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterator

BASE = "https://yuanbao.tencent.com"
P = "/api/v1/voice_recorder/"


class ApiError(RuntimeError):
    pass


class Client:
    def __init__(self, creds: dict, use_proxy: bool = False, timeout: float = 30):
        self.creds = creds
        self.timeout = timeout
        handlers = [] if use_proxy else [urllib.request.ProxyHandler({})]
        self.opener = urllib.request.build_opener(*handlers)

    def post(self, endpoint: str, body: dict | None = None) -> dict:
        headers = {
            **self.creds,
            "X-Source": "web",  # required; "pc"/"app" are rejected for desktop tokens
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 ybrec",
        }
        req = urllib.request.Request(BASE + P + endpoint, data=json.dumps(body or {}).encode(),
                                     headers=headers, method="POST")
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode(errors="replace")
            if e.code == 401:
                raise ApiError(f"鉴权失败（401）：{detail}。登录态可能已过期，请在元宝里重新登录。") from None
            raise ApiError(f"HTTP {e.code}: {detail}") from None
        if data.get("code") not in (0, None):
            raise ApiError(f"{endpoint}: code={data.get('code')} {data.get('message')}")
        return data.get("data") or {}

    # ---- endpoints -------------------------------------------------------

    def iter_voices(self) -> Iterator[dict]:
        """All recordings, newest first (server pages by 10)."""
        body: dict = {}
        while True:
            d = self.post("get_voices", body)
            voices = d.get("voices") or []
            yield from voices
            if not d.get("hasMore") or not voices:
                return
            body = {"startTime": voices[-1]["startTime"]}

    def detail(self, rid: str) -> dict:
        return self.post("get_voice_recorder", {"recorderId": rid}).get("voiceRecorder") or {}

    def sentences(self, rid: str) -> dict:
        return self.post("get_voice_sentence_v2", {"recorderId": rid})

    def summary(self, rid: str) -> dict:
        return self.post("get_voice_summary", {"recorderId": rid}).get("voiceSummary") or {}

    def minutes(self, rid: str) -> list:
        return self.post("get_voice_minutes", {"recorderId": rid}).get("voiceMinutes") or []

    def download(self, url: str, dest: str) -> int:
        """Download a signed COS URL to dest; returns bytes written."""
        tmp = dest + ".part"
        n = 0
        with self.opener.open(url, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                n += len(chunk)
        import os
        os.replace(tmp, dest)
        return n
