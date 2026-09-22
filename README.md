# verify-with-video

Turn “the fix works” into a short video showing the real action, visible result, and saved state.

把“已经修好了”变成一段看得见操作、变化与保存结果的验收视频。

[English](#english) · [中文](#中文)

## English

### What it does

A Codex skill for real UI acceptance recording: operate the target application, preserve the evidence, trim waiting, play ordinary actions at 2× speed, and add short Chinese narration. It delivers a compact H.264 MP4 and a concise account of what passed, failed, or was not covered.

- Native macOS input, screenshots, and ScreenCaptureKit recording; no built-in Computer Use dependency.
- Cooperative FIFO desktop queue with task ownership, release, and handoff notifications.
- Window/process identity checks, before/after screenshots, recording health logs, and raw footage.
- Save-and-reopen checks where persistence matters; no claiming UI success from scripts alone.
- Blender/Bonsai 3D acceptance footage must use **Perspective**, including the delivered result shots.

This is an agent workflow with native helper tools, not a one-command automatic video editor. The agent plans the interaction, inspects the footage, edits it, and aligns narration.

### Prerequisites

- [ ] **Codex on a Mac**, with shell access, a real task ID (`CODEX_THREAD_ID`), and task-message tools for queue handoffs. Install Codex using the official setup instructions below. A generic skill installer does not supply these host capabilities.
- [ ] **macOS 12.3+** for ScreenCaptureKit. Install macOS updates through System Settings → General → Software Update. The bundled native helper is macOS-only and needs a compatible current SDK; the minimum OS version alone does not guarantee your build works.
- [ ] **Apple Command Line Tools**: run `xcode-select --install`; verify with `xcrun swiftc --version`.
- [ ] **Homebrew**, if using the dependency commands below. Follow the official installer linked below; verify with `brew --version`.
- [ ] **Python, FFmpeg, uv, Git, and Bun**: run `brew install python ffmpeg uv git oven-sh/bun/bun`; verify with `python3 --version`, `ffmpeg -version`, `uv --version`, `git --version`, and `bun --version`.
- [ ] **Narration**: run `uv tool install edge-tts` and verify with `uv tool run --from edge-tts edge-tts --version`. The fallback uses macOS `say`; check `say -v '?'` for Tingting and install the Chinese voice through System Settings → Accessibility → Spoken Content / Read & Speak if needed.
- [ ] **Desktop permissions**: when macOS requests access, allow the relevant host/helper in Privacy & Security → Accessibility and Screen Recording (wording varies by macOS version). Input Monitoring may also be requested. A successful compile does not prove permissions are granted.

[Official Codex setup](https://developers.openai.com/codex/quickstart/)

[Homebrew installation](https://brew.sh/)

### Install and verify

1. Install for Codex in the current project, or add `--global` for a personal installation. This can replace an existing installation with the same name; preserve any local customizations first.

   ```bash
   bunx --bun skills add Weihan96/verify-with-video --agent codex --skill verify-with-video --yes
   bunx --bun skills list --agent codex
   ```

   For a global installation, use `--global` with both commands.

2. For an inspectable checkout and offline verification, clone the repository into a new folder:

   ```bash
   git clone https://github.com/Weihan96/verify-with-video.git
   cd verify-with-video
   python3 scripts/desktop.py --help
   python3 scripts/desktop.py build
   python3 -m unittest discover -s tests -v
   ```

   `build` compiles the control helper without taking over the desktop. The recorder is compiled separately on first recording. Tests use temporary state and mocked desktop operations; capture-guard tests compile Swift and exercise a temporary process. They do not record your screen or verify real UI behavior.

3. Start a Codex task that can discover the installed skill and invoke `$verify-with-video`. If it is not listed, reload the app or start a new task. First request a short, reversible UI probe; the agent must inspect the recorded result before a full acceptance run.

### Try saying

- “Use $verify-with-video to verify the settings fix. Show the change, save it, reopen it, and give me a short video.”
- “Record the Blender cabinet acceptance flow. Keep every 3D shot in Perspective and include the final result.”
- “Trim this existing recording, remove waiting, and add short Chinese narration. Do not operate the app again.”

### Scope and limits

The native helper controls the real desktop. Tasks on the same desktop must share one queue; it is cooperative coordination, not an operating-system lock. It cannot prevent interference from users or tools that ignore the queue. Never change `CODEX_HOME`, fake a task ID, or reset another task's queue to bypass waiting.

The workflow does not grant permission to edit application code, overwrite user files, or publish externally. Recording can include private content: select the correct window and inspect the capture before sharing. Narration via `edge-tts` sends narration text to an online speech service; macOS Tingting is the fallback. This project provides no paid service or API key, but your agent subscription, network, and optional hosting may have their own costs.

Only macOS native desktop operation is bundled. Linux can use the POSIX queue, but this repository does not provide Linux/Windows desktop drivers. English requests work, while the skill instructions and default narration are Chinese; request another narration language explicitly.

Optional integrations are **not bundled**: `on-mobile` for phone-accessible delivery, and `bonsai-launcher` for task-owned Blender launch workflows. Without them, deliver a local video and bind an already opened, verified task window; do not invent missing tools or claim the integrations were tested.

### Troubleshooting

| Symptom | What to do |
| --- | --- |
| `swiftc` missing or SDK compilation failure | Install/update Apple Command Line Tools with `xcode-select --install`; check `xcode-select -p` and `xcrun swiftc --version`, then rerun `build`. Keep the compiler error if it still fails. |
| Capture denied, blank recording, or clicks have no effect | Check Accessibility and Screen Recording permissions for the actual host/helper, verify the target window, and repeat a short reversible probe. Do not treat `sent` as proof of a click. |
| `CODEX_THREAD_ID required` | Run inside the real Codex task environment. Do not use a made-up ID or another task's ID; generic terminals may not supply the required host context. |
| Queue says `waiting` | Keep the ticket and wait for handoff. Do non-desktop work meanwhile; do not delete state or change the shared state directory. |
| Xiaoxiao narration is unavailable | Check `uv tool run --from edge-tts edge-tts --version` and network access; use installed Tingting if necessary and label the fallback. |
| Blender opens in Orthographic | Switch the recorded viewport to Perspective before the formal take. Verify again after reopening a file or changing views. |

### Development and credits

The repository includes queue, lifecycle, orchestration, and Swift capture-guard regression tests. They complement, and do not replace, recording real interactions.

Built by **Weihan96** using Python and Apple's macOS frameworks. Video processing uses **FFmpeg**, narration uses **rany2/edge-tts**, and skill distribution uses **Vercel Labs' skills CLI**. These upstream projects retain their own licenses; no third-party binaries or footage are bundled.

[Apple ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit)

[FFmpeg project](https://ffmpeg.org/)

[edge-tts by rany2](https://github.com/rany2/edge-tts)

[skills CLI by Vercel Labs](https://github.com/vercel-labs/skills)

## 中文

### 能做什么

让 Codex 用真实界面操作证明修复是否有效，并交付一段精简视频：删除等待，普通操作两倍速，关键结果保留足够时间，配上简短中文旁白。保存类操作要展示重开验证；不能用后台脚本成功代替界面验收。

内置 macOS 鼠标键盘、截图、录屏工具和共享桌面排队机制，核对进程与窗口归属，保留原片、操作记录和录制健康日志。Blender/Bonsai 的三维正式验收画面及成片必须使用 **Perspective 透视**。

这是供 agent 执行的验收流程及辅助工具，不是单条命令自动生成视频的应用。观察画面、选择剪点和对齐旁白仍由 agent 完成。

### 前置条件

- [ ] **Mac 上的 Codex**：通过上方官方链接安装，任务需要 shell、真实 `CODEX_THREAD_ID` 和队列交接用的任务消息工具；安装 skill 本身不会增加这些能力。
- [ ] **macOS 12.3 或更高版本及兼容 SDK**：通过系统设置 → 通用 → 软件更新安装更新；最低系统版本并不保证任意 SDK 都能编译。
- [ ] **Apple 命令行工具**：执行 `xcode-select --install`，用 `xcrun swiftc --version` 验证。
- [ ] **Homebrew**：通过上方 Homebrew 官方链接安装，用 `brew --version` 验证。
- [ ] **依赖工具**：执行 `brew install python ffmpeg uv git oven-sh/bun/bun`，分别用 `python3 --version`、`ffmpeg -version`、`uv --version`、`git --version`、`bun --version` 验证。
- [ ] **配音工具**：执行 `uv tool install edge-tts`，用 `uv tool run --from edge-tts edge-tts --version` 验证。离线回退依赖 macOS 婷婷，可用 `say -v '?'` 检查；缺少时从系统设置的辅助功能朗读设置安装中文声音。
- [ ] **系统权限**：根据系统提示，在隐私与安全性中给实际宿主及辅助程序授予辅助功能、屏幕录制权限；系统也可能请求输入监控。编译成功不等于权限已通过。

### 安装与验证

1. 在项目目录安装并检查发现结果；个人全局安装则给两条命令都加上 `--global`。同名安装可能被替换，请先保存自己的定制。

   ```bash
   bunx --bun skills add Weihan96/verify-with-video --agent codex --skill verify-with-video --yes
   bunx --bun skills list --agent codex
   ```

2. 需要检查源码和运行离线测试时，克隆到一个新目录：

   ```bash
   git clone https://github.com/Weihan96/verify-with-video.git
   cd verify-with-video
   python3 scripts/desktop.py --help
   python3 scripts/desktop.py build
   python3 -m unittest discover -s tests -v
   ```

   `build` 仅编译控制程序，录屏程序首次录制时单独编译。测试使用临时状态、模拟桌面接口及临时进程，不会操作真实应用、录制屏幕或占用正式队列，也不代表真实界面验收已经通过。

3. 在能发现技能的 Codex 任务中使用 `$verify-with-video`；若未显示，重新加载应用或开启新任务。先要求一次短时、可逆的操作录屏探针，查看视频确认操作与捕获都正常后再正式验收。

### 可以这样说

- “用 $verify-with-video 验收这个设置修复，展示修改、保存和重开，交付短视频。”
- “录屏验收 Blender 橱柜，三维画面全部使用透视，最后展示结果。”
- “把现有录屏剪短，删掉等待，加简短中文旁白，不要重新操作应用。”

### 限制与可选集成

原生工具会操作真实桌面。同一桌面的任务必须共享队列；队列是协作约定，不是系统锁，不能阻止人工输入或不遵守队列的其他工具。禁止更改 `CODEX_HOME`、伪造任务 ID 或清空别人的占用来插队。

录屏可能包含隐私信息，分享前应核对窗口和素材。技能不会额外授权改代码、覆盖文件或对外发布。晓晓配音使用在线服务，只提交需要配音的文字；失败时回退本机婷婷并说明。项目不提供收费服务或 API 密钥，但 agent 订阅、联网及可选媒体托管可能产生各自费用。

内置桌面工具仅支持 macOS；POSIX 队列可用于 Linux，但本仓库不提供 Linux/Windows 桌面驱动。说明和默认旁白为中文，可明确要求其他旁白语言。

手机链接用的 `on-mobile`、自动启动 Blender 用的 `bonsai-launcher` 是**未随包提供的可选集成**。没有时交付本地视频、绑定已打开且核实归属的任务窗口；不能虚构集成已安装或已验证。

### 常见问题

| 问题 | 处理方式 |
| --- | --- |
| 找不到 `swiftc` 或编译报 SDK 错误 | 安装或更新 Apple 命令行工具；检查 `xcode-select -p` 和 `xcrun swiftc --version` 后重新 `build`，仍失败则保留错误。 |
| 黑屏、录屏被拒绝或点击没有效果 | 核对实际宿主及辅助程序的系统权限、窗口归属，重做短探针；`sent` 只代表发送事件。 |
| 提示缺少 `CODEX_THREAD_ID` | 使用真正的 Codex 任务环境，不伪造或借用其他任务 ID；普通终端不一定有该上下文。 |
| 排队一直显示 `waiting` | 保留号码，等待交接，期间做不占桌面的准备；不删除状态或更换共享目录。 |
| 晓晓配音失败 | 检查工具版本和网络；有婷婷则回退并说明实际声音，没有可用声音就报告配音未完成。 |
| Blender 打开后是正交 | 正式录制前切换透视；重开文件或切换视图后再次核对。 |

### 致谢与许可证

由 **Weihan96** 发布，使用 Python 与 Apple 原生框架；感谢 FFmpeg 项目、rany2 的 edge-tts 和 Vercel Labs 的 skills CLI。上方提供了原项目链接。第三方依赖遵循各自许可证，本仓库不打包它们的二进制或用户录屏。

本仓库采用 MIT 许可证，详见 `LICENSE`。
