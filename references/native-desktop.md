# macOS 原生操作与取证

入口 `scripts/desktop.py`（Python 3 标准库）首次用系统 `swiftc` 将 `native.swift`、`capture_guard.swift` 和 `native-process.h` 按 control/recorder 分别编译到技能内 `.build/`，不得合并可执行文件身份。窗口截图用当前系统 SDK 可编译的 CoreGraphics，录屏用 macOS 12.3+ ScreenCaptureKit；需辅助功能／输入及屏幕录制权限。`build` 只编译、不占桌面；其余桌面命令须持共享队列凭据，不得直调底层二进制绕过检查。

## 定位与生命周期

`TOOL` 为本技能 `scripts/desktop.py` 绝对路径，`LEASE` 为 `desktop_queue.py request` 返回的凭据，`RUN` 为本任务独立取证目录。不得将示例固化为 PID、窗口、坐标或项目路径。

```bash
python3 "$TOOL" build
python3 "$TOOL" windows --lease-id "$LEASE" --work "$RUN"
python3 "$TOOL" launch --lease-id "$LEASE" --work "$RUN" --launch-record "$RUN/launch.json" --executable "$APP_EXECUTABLE" -- <应用参数>
python3 "$TOOL" windows --lease-id "$LEASE" --work "$RUN" --launch-record "$RUN/launch.json"
python3 "$TOOL" bind --lease-id "$LEASE" --work "$RUN" --session "$RUN/session.json" --window "$WINDOW" --launch-record "$RUN/launch.json"
python3 "$TOOL" restore --session "$RUN/session.json"
```

按领域启动流程确定参数。Blender 的 `launch` 增加 `--bonsai-launcher <bonsai-launcher.ts绝对路径> --worktree <本任务工作目录>`，应用参数改用启动器参数（如 `--blend <文件>`）；仅将启动器明确返回 `started` 的新进程登记为可关闭，`existing` 须只读核实后 attach。

`windows` 无进程参数时只列当前可见窗口；指定真实 `--launch-record`，或同时指定经核对的 `--pid` 与 `--executable` 时，只列该进程全部窗口，包括隐藏、最小化或其他 Space 中仍存在的窗口，返回 `onscreen` 和进程 `hidden/active`。列表可能含无标题辅助窗口，须按实际标题、边界、内容选定窗口 ID，不得凭同名应用猜测。

`bind` 可绑定上述不可见窗口，不自动发送输入。随后显式 `restore`：核对同一 PID/可执行文件/窗口，取消隐藏、激活、解除该窗口最小化并抬升，通过可见及前台焦点检查才截图。AX 匹配歧义或恢复失败即停止，不自动换窗口；其他 Space 的恢复依系统行为，未通过可见/焦点检查不得操作。隐藏窗口截图及普通 action 前截图仍会拒绝，须先恢复。

`launch` 只启动实际 GUI 程序，记录 PID、启动时刻、可执行文件；不得用后台脚本冒充界面验收。`windows` 返回真实 PID、窗口 ID、标题、全局坐标边界及权限状态，与场景/文件内容交叉确认后再 `bind`。绑定已有任务窗口可省略 `--launch-record`，但工具拒绝关闭它。仅当前工具实际启动且身份仍吻合的进程可 `close`；不得伪造启动记录。

启动后尚未成功 bind，可凭原始启动记录清理，无需伪造 session：

```bash
python3 "$TOOL" close --lease-id "$LEASE" --launch-record "$RUN/launch.json"
```

此路径核对当前任务、启动身份、可执行文件及 Bonsai 回执 owner，拒绝附加实例、错误/过期回执及仍有录屏的进程。仅发一次 SIGTERM 后等待确认退出，不强杀。启动参数不得覆盖当前任务身份。

同名应用不等于同一实例。每次调用复核进程启动身份、可执行文件、窗口归属及前台；另一普通窗口（含对话框）激活时，检查 `windows` 并用新会话文件明确绑定。窗口移动/缩放后须重新截图选点，不沿用旧图坐标。

## 输入与前后证据

```bash
python3 "$TOOL" snapshot --session "$RUN/session.json" --output "$RUN/before.png"
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"click","x":0.5,"y":0.5}'
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"key","code":1,"modifiers":["cmd"]}'
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"text","text":"probe"}'
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"reset"}'
```

- `x/y` 是**完整目标窗口图像**的归一化坐标：图上像素除以图像宽/高，范围 `[0,1)`。按当次窗口全局边界换算，不加固定标题栏偏移、不假定 Retina 倍率；裁切图先还原为完整窗口坐标。`snapshot` 的 JSON 侧文件记录窗口边界及像素尺寸。取证用原生窗口截图，不另开短时 ScreenCaptureKit 流，以免中断持续录屏；画面范围与边界不符即停止选点。
- `key.code` 是 macOS 虚拟键码（如 Return 36、Esc 53、Tab 48）；`modifiers` 为 `cmd/ctrl/shift/alt` 数组。组合键分别按下、逆向释放修饰键。Unicode `text` 不用剪贴板、不支持修饰键；应用不接收 Unicode 时改用真实按键，不静默后台赋值。
- `click` 支持 `button:"right"`、`count:2`；`move`、`scroll`（像素 `delta`）、`drag`（`to_x/to_y`）也须明确坐标。预期关闭对话框的动作增加 `--after-session <同进程主窗口session>` 指定后证据目标。成功动作有前后截图；失败时 `actions.jsonl` 保留错误及已取得证据，后截图可能缺失。`sent` 与 `ui_verified:false` 仅说明投递完成。
- 键盘以 HID 状态源向指定 PID 投递；鼠标通过前台及 AX 命中检查后以原生 HID 投递，设置当次窗口 ID。每次动作前后清理修饰键，异常时也清理已按下的键/鼠标。无持久 key-down 接口、全局服务或共享剪贴板修改。SIGINT/SIGTERM 请求原生清理；SIGKILL、系统崩溃或外部物理输入不保证自动恢复。异常退出后复核占用、日志、目标，再检查普通键与鼠标状态；不得将 `reset` 当作所有中断的修复。无法确认释放时保留占用并报告。
- 本节原生系统输入遇失焦、坐标被其他进程遮挡或目标消失即停止；已准入的 Blender 后台模拟输入不适用。窗口录屏是否继续取决于目标身份及录屏健康，失焦并非所有录屏模式的停止条件。不得靠不断激活/重发/坐标乱试证明稳定；查看前后证据、定位目标、做一次最小可逆动作，成功后跨调用重复验证。数值变化须检查结果区域，保存须重开读回。

## 短探针、录制与弹窗

```bash
python3 "$TOOL" record --session "$RUN/session.json" --output "$RUN/probe.mp4" --seconds 12
python3 "$TOOL" stop --session "$RUN/session.json"
python3 "$TOOL" record --session "$RUN/session.json" --output "$RUN/raw.mp4" --seconds 600
python3 "$TOOL" stop --session "$RUN/session.json"
```

`record` 首帧到达即输出 `first_frame` 就绪消息，录制结束才返回。命令持续运行于前台执行会话；调用工具用短 yield 保留运行 session，不 detach/nohup。到时自动停止，也可用 `stop` 请求正常结束并收集日志。输出 H.264 MP4，交付仍须按主文档转码为 yuv420p/faststart 并完整解码。日志保存首帧墙钟及媒体 PTS、输出尺寸、目标身份、结束帧数。操作时间对齐首帧，仅用于找剪点，结果是否入镜以实际帧为准。

默认仅录一个窗口，**不能保证包括另开的子窗口或菜单**。先录实际使用的弹窗/文件选择器探针并抽帧确认。需多窗口时，从 `snapshot` 返回的 displays 选择目标所在显示器，增加 `--display "$DISPLAY_ID"`：按明确窗口 ID 列表仅录该 PID 在该显示器上的窗口，录制中刷新新窗口；不得用应用过滤隔离同名多实例（系统可能合并同 bundle 进程）。新弹窗须留刷新时间，以探针确认入镜。跨显示器对话框须移回范围或另录，缺失步骤不能算已录。录制中不改窗口尺寸/显示器；需改时切段重做探针。

持续录屏以 libproc 读取的 PID、微秒级出生时间及可执行路径固定身份，复核不得采纳新身份。身份读取失败、进程退出、身份/路径变化或窗口 ID 换所有者，即失败收尾并记录具体原因。仅 CG 窗口查询返回空值或找不到原窗口时，容忍 2 秒单调时钟观测窗（非系统 API 调用硬超时）：记录 `target_observation_uncertain`，恢复时记录 `target_observation_recovered`；持续缺失或未确认期间结束均明确失败。复查不换窗口、不放宽过滤，普通输入仍须即时窗口/焦点/命中校验。每 10 秒 `capture_health` 记录身份检查数、窗口暂缺次数及帧数；静态窗口低帧数本身不代表录屏中断。

同任务同进程的各窗口 session 共用录像登记，防止对话框 session 提前 close。每次输入前后核对录屏健康，失败先 stop 收尾，不继续无录像操作。

队列凭据失效仍可用 `stop` 收尾自己的录屏，不授权继续输入。保留失败日志和素材；未成功结束的文件不能算通过。常规退出：停止输入 → 停止/收集录像 → 核对已保存证据和持久数据 → `close` 关闭自己启动的临时进程 → 确认退出 → 释放队列并通知。`close` 发 SIGTERM、不代保存；须先在应用内保存重开，不得关闭用户/其他任务进程。

## 诊断边界

| 现象 | 下一步 |
|---|---|
| 全局 windows 看不到已启动窗口 | 凭原始 launch-record 限定进程查询；选定窗口后 bind、restore。仍无窗口则查启动日志，必要时凭回执 close；不伪造 session。 |
| 事件返回 sent，控件不变 | 查前后图、活动窗口、焦点、坐标，仅做最小可逆探针；不得改脚本直接设置业务状态后宣称鼠标成功。 |
| 键盘可用、鼠标不变 | 核对完整窗口像素/点换算、最新窗口 ID 及弹窗是否另开窗口。 |
| 修饰键残留 | 同一目标执行 reset，再录单键和组合键两轮；不得全局释放他人输入。 |
| 录屏过一段时间误报目标消失 | 保留具体身份/查询错误、health 时间线及失败后定向窗口证据，不吞错为统一“消失”或无界重试。按原模式做超过失败时长的数分钟操作、截图、弹窗及空闲回归。 |
| 录屏拒绝、无首帧、文件损坏 | 留存日志，报告本轮录屏未完成；不重置系统录屏/权限服务，不用截图补作视频通过。 |
| 保存后文件值不符 | 分别核对“编辑草稿→应用更新→保存→重开”；后台读文件仅作持久化辅助证据。 |

ScreenCaptureKit 窗口与应用过滤依据 Apple 文档：

[SCContentFilter](https://developer.apple.com/documentation/screencapturekit/sccontentfilter)
