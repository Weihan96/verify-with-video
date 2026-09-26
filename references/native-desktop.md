# macOS 原生操作与取证

入口为 `scripts/desktop.py`（Python 3 标准库），首次运行使用系统 `swiftc` 将 `native.swift`、`capture_guard.swift` 和 `native-process.h` 按 control/recorder 两个角色分别编译到技能内 `.build/`，不可合并成同一可执行文件身份。使用当前系统 SDK 可编译的 CoreGraphics 窗口截图及 macOS 12.3+ 的 ScreenCaptureKit 录屏，需要辅助功能／输入与屏幕录制权限。`build` 只编译，不占桌面；其余桌面命令须持有共享队列凭据。不要直接调用底层二进制绕过凭据检查。

## 定位与生命周期

以下以 `TOOL` 代表本技能 `scripts/desktop.py` 的绝对路径。`LEASE` 使用 `desktop_queue.py request` 返回的凭据；`RUN` 使用本任务独立的取证目录。不要复制示例为固定 PID、窗口、坐标或项目路径。

```bash
python3 "$TOOL" build
python3 "$TOOL" windows --lease-id "$LEASE" --work "$RUN"
python3 "$TOOL" launch --lease-id "$LEASE" --work "$RUN" --launch-record "$RUN/launch.json" --executable "$APP_EXECUTABLE" -- <应用参数>
python3 "$TOOL" windows --lease-id "$LEASE" --work "$RUN" --launch-record "$RUN/launch.json"
python3 "$TOOL" bind --lease-id "$LEASE" --work "$RUN" --session "$RUN/session.json" --window "$WINDOW" --launch-record "$RUN/launch.json"
python3 "$TOOL" restore --session "$RUN/session.json"
```

先按领域启动流程决定启动参数。Blender 启动时给 `launch` 增加 `--bonsai-launcher <bonsai-launcher.ts绝对路径> --worktree <本任务工作目录>`，应用参数换成该启动器的参数（例如 `--blend <文件>`）；工具仅将启动器明确返回 `started` 的新进程登记为可关闭，`existing` 必须只读核实后 attach。

`windows` 不带进程参数时只列当前可见窗口。指定真实 `--launch-record`，或同时指定经核对的 `--pid` 与 `--executable` 时，只枚举该进程的所有窗口，包括隐藏、最小化或其他 Space 中仍存在的窗口；返回 `onscreen` 和进程 `hidden/active`。列表也可能含无标题辅助窗口，必须按实际标题、边界和内容选择明确窗口 ID，不能按同名应用猜测。

`bind` 允许绑定上述不可见窗口，但不会自动发送输入。随后显式 `restore`：核对同一 PID/可执行文件/窗口，取消隐藏、激活、解除该窗口最小化并抬升，再检查可见及前台焦点，成功才截图。AX 匹配歧义或恢复失败时停止，不能自动换窗口；其他 Space 的恢复取决于系统行为，未通过可见/焦点检查就不能操作。隐藏窗口截图及普通 action 的前截图仍会拒绝，先恢复再继续。

`launch` 只启动实际 GUI 程序并记录 PID、启动时刻和可执行文件；不能用它运行后台脚本冒充界面验收。`windows` 返回真实 PID、窗口 ID、标题、全局坐标边界和权限状态。用这些信息与场景/文件内容交叉确认目标，再 `bind`。绑定已有任务窗口可省略 `--launch-record`，但工具将拒绝关闭它。只有当前工具实际启动且身份仍吻合的进程可 `close`；不要伪造启动记录。

若启动后尚未成功 bind，仍可只凭原始启动记录清理，不需要伪造 session：

```bash
python3 "$TOOL" close --lease-id "$LEASE" --launch-record "$RUN/launch.json"
```

此路径核对当前任务、启动身份、可执行文件及 Bonsai 回执 owner；拒绝附加实例、错误/过期回执和仍有录屏的进程。只发送一次 SIGTERM，然后等待确认退出，不升级为强杀。启动参数不得覆盖当前任务身份。

同名应用不等于同一实例。每次调用重新核对进程启动身份、可执行文件、窗口归属和前台；另一普通窗口（含对话框）变为活动窗口时，检查 `windows` 并用新会话文件明确绑定它。窗口移动/缩放后重新截图和选点，不能继续套旧截图坐标。

## 输入与前后证据

```bash
python3 "$TOOL" snapshot --session "$RUN/session.json" --output "$RUN/before.png"
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"click","x":0.5,"y":0.5}'
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"key","code":1,"modifiers":["cmd"]}'
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"text","text":"probe"}'
python3 "$TOOL" action --session "$RUN/session.json" --action '{"op":"reset"}'
```

- `x/y` 是**完整目标窗口图像**的归一化坐标：图上像素除以图像宽/高，范围 `[0,1)`。工具按当次窗口全局边界换算，不加固定标题栏偏移，不假定 Retina 倍率。局部裁切图片先还原到完整窗口坐标。`snapshot` 的 JSON 侧文件记录窗口边界与像素尺寸。取证使用原生窗口截图，不另开短时 ScreenCaptureKit 流，避免中断持续录屏；出现画面范围与边界不一致时停止选点。
- `key.code` 是 macOS 虚拟键码（例如 Return 36、Esc 53、Tab 48）；`modifiers` 为 `cmd/ctrl/shift/alt` 数组。组合键会分别按下并逆向释放修饰键。Unicode `text` 不使用剪贴板，不支持带修饰键；应用不接收 Unicode 时改为真实按键输入，不静默改用后台赋值。
- `click` 支持 `button:"right"`、`count:2`；`move`、`scroll`（像素 `delta`）、`drag`（`to_x/to_y`）也要求明确坐标。预期动作会关闭对话框时，增加 `--after-session <同进程主窗口session>` 指定后证据目标。成功动作有前后截图；失败动作在 `actions.jsonl` 保留错误及已取得的证据，后截图可能不存在。返回的 `sent` 与 `ui_verified:false` 只说明投递完成。
- 键盘使用 HID 状态源向指定 PID 投递；鼠标经前台与 AX 命中检查后走原生 HID 投递，并设置当次窗口 ID；每次动作前后清理修饰键，异常路径也清理已按下的键/鼠标。没有持久的 key-down 接口，也没有全局服务或共享剪贴板修改。SIGINT/SIGTERM 会请求原生清理；SIGKILL、系统崩溃或外部物理输入不保证自动恢复。异常退出后重新核对占用、日志和目标，再检查普通键与鼠标状态，不能把 `reset` 当作一切中断的修复；无法确认释放时保留占用并报告。
- 本节原生系统输入在前台失去、坐标被其他进程遮挡或目标消失时停止输入。此规则不适用于已准入的 Blender 后台模拟输入；窗口录屏是否继续由目标身份与录屏健康决定，不把“失焦”当作所有录屏模式的停止条件。不可通过不断激活/重发/坐标乱试证明稳定；查看前后证据、定位目标和一次最小可逆动作，成功后跨调用重复验证。数值变化需检查结果区域，保存还要重开读回。

## 短探针、录制与弹窗

```bash
python3 "$TOOL" record --session "$RUN/session.json" --output "$RUN/probe.mp4" --seconds 12
python3 "$TOOL" stop --session "$RUN/session.json"
python3 "$TOOL" record --session "$RUN/session.json" --output "$RUN/raw.mp4" --seconds 600
python3 "$TOOL" stop --session "$RUN/session.json"
```

`record` 首帧到达后输出 `first_frame` 就绪消息，录制结束才完成返回。录制命令在前台执行会话中持续运行，调用工具用短 yield 保留运行 session，不要 detach/nohup；到时自动停止，也可用 `stop` 请求正常结束并收集日志。输出 H.264 MP4；最后交付仍需按主文档转码为 yuv420p/faststart 并完整解码。日志保存首帧墙钟与媒体 PTS、输出尺寸、目标身份、结束帧数。操作时间以首帧对齐，只用于找剪点，实际帧决定结果是否入镜。

默认仅录一个窗口。单窗口过滤**不能保证包括另开的子窗口或菜单**。先录实际使用的弹窗/文件选择器探针并抽帧确认；需要多个窗口时，从 `snapshot` 返回的 displays 选择目标所在显示器，录制增加 `--display "$DISPLAY_ID"`：按明确窗口 ID 列表仅包括该 PID 在该显示器上的窗口，录制期间刷新新窗口；不能使用应用过滤来隔离同名多实例（系统可能合并同 bundle 的进程）。新弹窗需留出刷新时间，并用探针确认实际入镜。跨显示器对话框需移回范围或另录，不能把缺失步骤算已录到。录制中不要改变窗口尺寸/显示器；需要改变时切段并重新探针。

持续录屏以 libproc 读取的 PID、微秒级出生时间和可执行路径固定进程身份，每次核对不得重新采纳新身份。身份读取失败、进程退出、身份/路径变化或窗口 ID 换了所有者，立即失败收尾并记录具体原因。仅 CG 窗口查询返回空值或未找到原窗口时，使用 2 秒单调时钟观测容忍窗（不是系统 API 调用的硬超时）：记录 `target_observation_uncertain`、恢复时的 `target_observation_recovered`；持续缺失或在未确认期间结束都明确失败。复查不切换窗口或放宽过滤范围，普通输入仍要求即时窗口/焦点/命中校验。每 10 秒 `capture_health` 记录身份检查数、窗口暂缺次数与帧数；静态窗口低帧数本身不等于录屏中断。

同一任务同一进程的多个窗口 session 共用录像登记，防止对话框 session 提前 close。每次输入前后核对录屏健康，失败先 stop 收尾，不继续无录像操作。

`stop` 即使队列凭据失效也允许收尾自己的录屏，但不会授权继续输入。录制失败的日志和素材必须保留；未成功结束的文件不能当作通过。常规退出顺序：停止输入 → 停止/收集录像 → 核对已保存证据和持久数据 → `close` 关闭自己启动的临时进程 → 确认退出 → 释放队列并通知。`close` 发 SIGTERM，不会替你保存；必须先完成应用内保存重开，不能关闭用户/其他任务进程。

## 诊断边界

| 现象 | 下一步 |
|---|---|
| 全局 windows 看不到已启动窗口 | 用原始 launch-record 做进程限定查询；选定窗口后 bind、restore。仍无窗口时核对启动日志，必要时凭回执 close；不伪造 session。 |
| 事件返回 sent，控件不变 | 检查前后图、活动窗口、焦点和坐标；只做最小可逆探针。不能改脚本直接设置业务状态后宣称鼠标成功。 |
| 键盘可用、鼠标不变 | 核对完整窗口像素/点换算和最新窗口 ID；检查弹窗是否另开窗口。 |
| 修饰键残留 | 同一目标执行 reset，再录单键和组合键两轮；不得全局释放他人输入。 |
| 录屏过一段时间误报目标消失 | 保留具体身份/查询错误、health 时间线和失败后定向窗口证据；不能吞错成统一“消失”或无界重试。按原模式进行超过失败时长的数分钟操作、截图、弹窗及空闲回归。 |
| 录屏拒绝、无首帧、文件损坏 | 保留日志，报告本轮录屏未完成；不重置系统录屏/权限服务，不改用截图补成视频通过。 |
| 保存后文件值不符 | 分开核对“编辑草稿→应用更新→保存→重开”；后台读文件仅为持久化辅助证据。 |

ScreenCaptureKit 的窗口与应用过滤依据 Apple 文档：

[SCContentFilter](https://developer.apple.com/documentation/screencapturekit/sccontentfilter)
