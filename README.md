# ybrec — 元宝录音笔 CLI

用命令行获取**你自己的**腾讯元宝「AI 录音笔」录音：原始音频（m4a）、逐句转写（带说话人）、AI 总结和章节纪要，并能增量同步到本地目录。写这个工具，是为了让 AI agent（Claude Code、Codex 等）直接读到你的会议录音，帮你整理和跟进个人工作。

> ⚠️ **非官方工具**，与腾讯公司、腾讯元宝没有任何关联。它调用的是元宝网页前端使用的**未公开接口**，元宝改版后随时可能失效。只能用来获取自己账号下的数据。
>
> 📄 **仅限个人非商业使用，禁止私自商用。** 商用请联系作者授权：neohuiqixue@foxmail.com。详见 [LICENSE](LICENSE)。

## 原理

元宝的录音存在云端：录音时边录边上传，手机和电脑登录同一账号就能看到同样的录音。ybrec 用你的登录态调用元宝前端自己也在用的接口：

| 接口 | 用途 |
|---|---|
| `voice_recorder/get_voices` | 录音列表（每页 10 条，按 `startTime` 翻页） |
| `voice_recorder/get_voice_recorder` | 录音详情，含音频的签名下载地址 |
| `voice_recorder/get_voice_sentence_v2` | 逐句转写与说话人 |
| `voice_recorder/get_voice_summary` / `get_voice_minutes` | AI 总结 / 章节纪要 |

ybrec 只调用读取类接口，不会删除或修改你的任何录音。

登录态从**元宝桌面版**（Windows，WebView2 内核）获取：用调试端口启动桌面版，再通过 Chrome DevTools Protocol 读出页面里的登录 token。token 由元宝自己续期，ybrec 不保存它。

## 安装

需要 Python ≥ 3.9。

```bash
uv tool install git+https://github.com/NeoFantom/yuanbao-recorder-cli
# 或者
pipx install git+https://github.com/NeoFantom/yuanbao-recorder-cli
```

## 快速开始（Windows / WSL）

```bash
ybrec desktop          # 强制关闭并以调试模式重启元宝桌面版（默认端口 9229），在窗口里登录
ybrec auth             # 检查登录态：OK  source=desktop:9229 ...
ybrec list -n 5        # 最近 5 条录音
ybrec transcript 1f2e  # 逐句转写（recorderId 可以只写前缀）
ybrec summary 1f2e     # AI 总结 + 章节纪要
ybrec audio 1f2e       # 下载 m4a
ybrec sync ~/yuanbao   # 增量同步全部录音
```

- **WSL**：需要开启 mirrored 网络模式（在 `%USERPROFILE%\.wslconfig` 的 `[wsl2]` 下写 `networkingMode=mirrored`），WSL 里才能访问 Windows 的 `127.0.0.1:9229`。
- **其他平台 / 自备 token**：设置环境变量 `YBREC_X_ID` 和 `YBREC_X_TOKEN` 即可跳过桌面版。这两个值就是元宝桌面版 localStorage 里的 `X-ID`、`X-Token`。网页版登录态能否这样用，目前**未验证**。

## 命令

| 命令 | 说明 |
|---|---|
| `ybrec desktop [--exe PATH]` | 以调试端口（重新）启动元宝桌面版（Windows/WSL） |
| `ybrec auth` | 检查登录态是否可用 |
| `ybrec list [-n N] [--json]` | 列出录音，新的在前 |
| `ybrec show ID` | 录音详情（JSON） |
| `ybrec transcript ID [--json]` | 逐句转写（Markdown） |
| `ybrec summary ID [--json]` | AI 总结 + 章节纪要（Markdown） |
| `ybrec audio ID [-o FILE]` | 下载原始音频 |
| `ybrec sync DIR [-n N] [--no-audio] [--force]` | 增量同步 |

通用选项：`--port`（默认 9229，也可用环境变量 `YBREC_PORT`），`--proxy`（使用环境变量里的 HTTP 代理；默认直连，因为国内服务走境外代理会很慢）。

### sync 的目录结构

```
DIR/
  2026-11-19_0943_周会_1f2e3d4c/
    meta.json        # 列表 + 详情元数据（不含会过期的音频签名地址）
    audio.m4a
    transcript.md
    summary.md
    .complete        # 有这个文件就跳过；还在处理中的录音下次 sync 会重试
```

一条录音同时满足下面几条，才算完成：录音状态为已结束、转写已完成、总结已完成或这条录音没有总结（很短的录音可能不生成总结）。这些状态码是作者观察得出的，元宝没有公开文档。

## 给 AI agent 的用法

把下面这段放进 agent 的项目说明（如 `AGENTS.md` / `CLAUDE.md`）：

```
需要我的会议录音内容时，用 `ybrec`：
- 先 `ybrec auth`；报连不上调试端口时让我运行 `ybrec desktop` 并登录元宝。
- `ybrec list -n 20 --json` 找录音，`ybrec summary <id>` 看总结，需要细节再看 `ybrec transcript <id>`。
- 批量处理用 `ybrec sync <dir> --no-audio`，然后直接读目录里的 Markdown。
```

## 注意事项

- **调试端口的安全性**：调试端口开着时，本机任何程序都能控制元宝桌面版。不用时请正常退出并重开元宝，端口就会关闭。
- 接口未公开，字段和鉴权方式随时可能变化。失效时欢迎提 issue。
- 音频下载地址是带签名的临时链接，ybrec 不会把它写进 `meta.json`。

## 许可与联系

- 仅限个人、非商业使用，用于方便 AI agent 处理你自己的工作资料。**禁止私自商用**，商用需联系作者授权。
- 如果认为本项目侵犯了您的权益，请联系作者，会及时处理。
- 作者：Neo — neohuiqixue@foxmail.com

---

### English

`ybrec` is an **unofficial** CLI that fetches *your own* Tencent Yuanbao AI-recorder data (audio, transcripts, summaries) so personal AI agents can work with it. It reads the login token from the Yuanbao Windows desktop app through a WebView2 remote-debugging port and calls the same undocumented read-only endpoints the web front end uses. Not affiliated with Tencent. **Personal non-commercial use only. Commercial use requires written permission.** For licensing or infringement concerns, contact neohuiqixue@foxmail.com.
