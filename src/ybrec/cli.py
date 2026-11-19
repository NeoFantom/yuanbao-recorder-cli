"""ybrec — fetch your own Tencent Yuanbao (元宝) AI-recorder recordings."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, auth, render
from .api import ApiError, Client


def _client(a) -> Client:
    return Client(auth.get_credentials(a.port), use_proxy=a.proxy)


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _find(c: Client, rid: str) -> dict:
    """Resolve a full or prefix recorder id to its list entry."""
    for v in c.iter_voices():
        if v["recorderId"].startswith(rid):
            return v
    raise ApiError(f"找不到录音 {rid}")


# ------------------------------------------------------------------ commands

def cmd_desktop(a):
    print(f"将强制关闭并以调试端口 {a.port} 重新启动元宝桌面版……", file=sys.stderr)
    auth.launch_desktop(a.port, a.exe)
    print("已就绪。若元宝未登录，请在窗口里登录。", file=sys.stderr)


def cmd_auth(a):
    creds = auth.get_credentials(a.port)
    src = "env" if auth.from_env() else f"desktop:{a.port}"
    n = next(Client(creds, use_proxy=a.proxy).iter_voices(), None)
    print(f"OK  source={src}  user={creds['X-ID'][:4]}***  recordings={'yes' if n else 'none'}")


def cmd_list(a):
    c = _client(a)
    rows = []
    for i, v in enumerate(c.iter_voices()):
        if a.limit and i >= a.limit:
            break
        rows.append(v)
    if a.json:
        return _out(rows)
    for v in rows:
        print(f"{v['recorderId']}  {render.ts(v.get('startTime'))}  {render.duration(v.get('durationMs')):>8}  {v.get('title', '')}")


def cmd_show(a):
    c = _client(a)
    rid = _find(c, a.id)["recorderId"]
    d = c.detail(rid)
    d.pop("waveforms", None)
    _out(d)


def cmd_transcript(a):
    c = _client(a)
    meta = _find(c, a.id)
    data = c.sentences(meta["recorderId"])
    _out(data) if a.json else print(render.transcript_md(meta, data), end="")


def cmd_summary(a):
    c = _client(a)
    meta = _find(c, a.id)
    s, m = c.summary(meta["recorderId"]), c.minutes(meta["recorderId"])
    _out({"summary": s, "minutes": m}) if a.json else print(render.summary_md(meta, s, m), end="")


def cmd_audio(a):
    c = _client(a)
    meta = _find(c, a.id)
    url = c.detail(meta["recorderId"]).get("audioFileUrl")
    if not url:
        raise ApiError("这条录音没有音频地址（可能仍在处理中）。")
    dest = a.output or f"{render.safe_name(meta.get('title'))}_{meta['recorderId'][:8]}.m4a"
    n = c.download(url, dest)
    print(f"{dest}  {n / 1e6:.1f} MB")


def cmd_sync(a):
    """Incremental mirror: one folder per recording; finished ones are skipped."""
    c = _client(a)
    os.makedirs(a.dir, exist_ok=True)
    existing = {}
    for name in os.listdir(a.dir):
        p = os.path.join(a.dir, name, "meta.json")
        if os.path.isfile(p):
            try:
                existing[json.load(open(p, encoding="utf-8"))["recorderId"]] = os.path.join(a.dir, name)
            except (ValueError, KeyError):
                pass
    done = new = 0
    for i, v in enumerate(c.iter_voices()):
        if a.limit and i >= a.limit:
            break
        rid = v["recorderId"]
        folder = existing.get(rid) or os.path.join(
            a.dir, f"{render.ts(v.get('startTime')).replace(':', '').replace(' ', '_')}_{render.safe_name(v.get('title'))}_{rid[:8]}")
        if not a.force and os.path.exists(os.path.join(folder, ".complete")):
            done += 1
            continue
        os.makedirs(folder, exist_ok=True)
        try:
            ok = _sync_one(c, v, folder, a)
        except ApiError as e:
            print(f"  ! {v.get('title')}: {e}", file=sys.stderr)
            continue
        new += 1
        if ok:
            open(os.path.join(folder, ".complete"), "w").close()
        print(f"{'✓' if ok else '…'} {os.path.basename(folder)}" + ("" if ok else "  （未完成，下次 sync 重试）"))
    print(f"同步结束：本次处理 {new} 条，已完成跳过 {done} 条。", file=sys.stderr)


def _sync_one(c: Client, v: dict, folder: str, a) -> bool:
    rid = v["recorderId"]
    detail = c.detail(rid)
    detail.pop("waveforms", None)
    json.dump({**v, **detail, "audioFileUrl": None}, open(os.path.join(folder, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    # Status codes observed (not documented): recording 4 = finished,
    # asrStatus 3 = transcript done, summary status 3 = done. `isCompleted` is
    # always False in practice, so it is ignored. Very short recordings may get
    # no summary at all (status None); that counts as done.
    ok = v.get("status") == 4
    if not a.no_audio:
        audio = os.path.join(folder, "audio.m4a")
        if not os.path.exists(audio):
            if detail.get("audioFileUrl"):
                c.download(detail["audioFileUrl"], audio)
            else:
                ok = False
    sent = c.sentences(rid)
    if sent.get("voiceSentence"):
        open(os.path.join(folder, "transcript.md"), "w", encoding="utf-8").write(render.transcript_md(v, sent))
    if sent.get("asrStatus") != 3:
        ok = False
    s, m = c.summary(rid), c.minutes(rid)
    if s.get("summary") or m:
        open(os.path.join(folder, "summary.md"), "w", encoding="utf-8").write(render.summary_md(v, s, m))
    if s.get("status") not in (3, None):
        ok = False
    return ok


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ybrec", description="获取自己的腾讯元宝 AI 录音笔录音、转写和总结（非官方）。")
    p.add_argument("--version", action="version", version=f"ybrec {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", type=int, default=int(os.environ.get("YBREC_PORT", auth.DEFAULT_PORT)),
                        help="元宝桌面版 WebView2 调试端口（默认 9229）")
    common.add_argument("--proxy", action="store_true", help="使用环境变量里的 HTTP 代理（默认直连，国内服务走代理很慢）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("desktop", parents=[common], help="以调试模式（重新）启动元宝桌面版（Windows/WSL）")
    s.add_argument("--exe", default=auth.DEFAULT_EXE, help="yuanbao.exe 路径")
    s.set_defaults(func=cmd_desktop)

    sub.add_parser("auth", parents=[common], help="检查登录态是否可用").set_defaults(func=cmd_auth)

    s = sub.add_parser("list", parents=[common], help="列出录音（新→旧）")
    s.add_argument("-n", "--limit", type=int, default=0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    for name, fn, hlp in [("show", cmd_show, "录音详情（JSON）"),
                          ("transcript", cmd_transcript, "逐句转写（Markdown，带说话人）"),
                          ("summary", cmd_summary, "AI 总结 + 纪要（Markdown）")]:
        s = sub.add_parser(name, parents=[common], help=hlp)
        s.add_argument("id", help="recorderId（可只写前缀）")
        if name != "show":
            s.add_argument("--json", action="store_true", help="输出原始 JSON")
        s.set_defaults(func=fn)

    s = sub.add_parser("audio", parents=[common], help="下载原始音频（m4a）")
    s.add_argument("id")
    s.add_argument("-o", "--output")
    s.set_defaults(func=cmd_audio)

    s = sub.add_parser("sync", parents=[common], help="增量同步全部录音到本地目录")
    s.add_argument("dir")
    s.add_argument("-n", "--limit", type=int, default=0, help="只看最新 N 条")
    s.add_argument("--no-audio", action="store_true", help="不下载音频，只要文字")
    s.add_argument("--force", action="store_true", help="忽略已完成标记，重新拉取文字（已有音频不重下）")
    s.set_defaults(func=cmd_sync)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        a.func(a)
    except (auth.AuthError, ApiError) as e:
        print(f"ybrec: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
