# Blender 后台输入与录屏

适用 macOS、Blender 4.5.3 LTS、真实 Codex task 自有临时验收实例。单任务可独立准备、准入、后台输入及录屏；已有多任务安排时，协调者可串行准备两个不同 macOS Space 的原生全屏窗口。正式准入后立即释放准备凭据，窗口内部事件与录屏继续；其他 task 可正常取桌面队列，用户可继续用前台其他应用。这不是多个系统鼠标，也非所有 Blender 功能的通用无焦点驱动。

代码随技能安装，保留 `experiments/cross_task/` 已测试的导入、接入路径；勿用历史 `experiments/isolation/` 同会话原型替代。`SKILL` 为当前安装目录；`GROUP`、`RUN`、真实 task ID 和租约均取本次工具返回值，不抄旧证据。

需保存、重开文件、操作独立弹窗或用未支持快捷键时，起初就选普通原生串行流程。现有并行实例不能中途切回原生输入；途中发现此需求，停止自己的输入与录制，保留未保存实例并报告，不得关闭或重开丢弃草稿、冒充串行保存。仅明确可丢弃的工作副本可正常关闭。

## 单任务入口（普通 Blender 后台验收默认）

`BG` 为本技能 `scripts/blender_background.py` 绝对路径。用当前真实 `CODEX_THREAD_ID`，不建辅助任务或伪造身份。先按桌面队列取得本次 `LEASE`，选新的绝对路径 `RUN`：

```bash
python3 "$BG" prepare --lease "$LEASE" --run "$RUN" --blend "$WORKFILE"
```

`--blend` 打开获授权工作副本，省略则保留启动场景；仅明确测试临时控件时用 `--fixture`。`--blender` 可指定可执行文件。

IFC/Bonsai 无须先另存 `.blend`。先读已安装的 `bonsai-launcher` 技能，用实际项目工作目录、获授权的 IFC 副本及项目已有初始化脚本：

```bash
python3 "$BG" prepare --lease "$LEASE" --run "$RUN" \
  --ifc "$IFC_COPY" --worktree "$PROJECT" \
  --prepare-script "$PROJECT_BOOTSTRAP" --task-title "$ACTUAL_TASK_TITLE"
```

无须项目插件则省略 `--prepare-script`。`--blend`、`--ifc`、`--fixture` 互斥。`--task-title` 用当前任务实际标题；省略则不设标题，保留启动器默认场景名。默认复用 `$CODEX_HOME/skills/bonsai-launcher/scripts/bonsai-launcher.ts`（未设置 CODEX_HOME 时为 `~/.codex`）；其他安装位置用 `--bonsai-launcher` 指定，不为此更改 CODEX_HOME。依赖不随技能打包，缺失则建组前报错。

适配器复用启动器任务锁、IFC loader、`--no-save` 及真实归属回执，加入后台输入参数；IFC/项目初始化后启动接收器，保留业务场景。准备须等 IFC 成功回执和接收器均就绪，核对源文件散列、PID、未保存 `.blend` 及警告状态；默认最多 120 秒，`--prepare-timeout` 可调至 600 秒。初始化失败或超时不算成功，保留自己的启动凭据供清理。先检查项目初始化脚本；若要求外部窗口、未授权写入或改变文件，先解决该问题。

普通实例不会自动转为后台实例。启动冲突时保留原实例，不加替换参数或伪造身份绕过归属锁；检查现有实例/草稿后再决定，不要仅因现有窗口失焦要求用户“现在录”。IFC 路径不覆盖未保存场景，也不新增保存、文件对话框等支持。

计划生成失败、Bun 子进程无法创建或明确返回 `existing` 时，仅删本次未启动占位回执，随后可正常关闭空准备组。进入启动器后报错、输出损坏或通信中断均属启动状态不确定：保留占位及错误，核对启动器状态、任务锁 owner 和日志后再处理；一次查不到 PID 不证明未启动，不删锁、不猜 PID。锁冲突无结构化未启动回执时，同样保留不确定状态。

脚本完成单任务建组、授权、启动后返回截图；查看 `RUN/A/prepared.png`（IFC 另有 `RUN/A/ifc-ready.json`），核对实际文件、窗口、Perspective、项目插件及控件坐标后执行：

```bash
python3 "$BG" admit --run "$RUN"
```

`admit` 固定同任务实例归属并立即释放准备租约；按 `handoff.notify` 通知队首，成功后登记。准备或准入失败时保留 run、启动回执及准备租约，检查后清理自己的实例；不得提前释放后强行准入。准入后交接中断可用 `admit` 完成。

启动有限时长服务，保留工具执行 session，不 detach；输出 `ready` 后再录制：

```bash
python3 "$BG" serve --run "$RUN" --seconds 1200
python3 "$BG" start --run "$RUN"
python3 "$BG" send --run "$RUN" --events "$EVENTS_JSON"
python3 "$BG" stop --run "$RUN"
```

保持 `serve` 运行，其他命令用独立工具调用执行。`start` 等首帧，`stop` 排空输入并严格解码本段；续录再 `start`。先短片确认控件实际响应，再正式操作。支持事件、坐标、日志及抽帧见下节，与多任务共用实现。正式阶段无需前台焦点，不因 Blender 不在前台停录或要求用户“现在录”；本入口不自动切换原生输入。

确认临时场景可关闭，先 `stop`（失败录像用 `collect` 保留失败信息），再执行：

```bash
python3 "$BG" close --run "$RUN"
```

`close` 关闭本任务实例、收尾服务并关闭组，不代为保存、不丢弃活跃录像、不改其他任务队列。准备失败但仍持准备租约时也可 `close`，成功后另行 release 准备租约并交接。录制启动中断，先 `collect` 收集本次待启动录制再重试；未就绪录制不能授权输入。失败后用 `status --run "$RUN"` 查看保留状态。资源清理不代表录像成功：服务有失败日志，关闭结果仍保留 `capture_outcome: failed`。源码复用 `experiments/cross_task/`；单、多任务的 token、PID、窗口、首帧、排空及录制校验一致。

## 多任务建组和准备

仅已有两个真实参与任务的并行验收用本节；普通单任务用上述入口。

1. 协调者按 [桌面队列](desktop-queue.md) 取凭据。复用两个明确参与的真实 task；用户要求新建时用任务工具创建，不以同会话两个脚本冒充。本入口固定两个参与者，协调者为第三个 task；不为单任务录屏建此安排。
参与者的组内后台操作不申请全局队列；独立前台应用工作仍按普通流程申请自己的队列凭据，不复用后台权限。
2. 协调者建组并授权 A 准备：

   ```bash
   python3 "$SKILL/experiments/cross_task/group.py" create --lease "$LEASE" --run "$RUN" --member "A=$TASK_A" --member "B=$TASK_B"
   python3 "$SKILL/experiments/cross_task/group.py" grant --group "$GROUP" --label A
   ```

3. A 在自己真实 task 环境执行：

   ```bash
   python3 "$SKILL/experiments/cross_task/prepare.py" "$GROUP" --blend "$WORKFILE"
   ```

   场景参数同单任务入口；IFC 可将 `--blend` 换为 `--ifc`、`--worktree` 及可选的 `--prepare-script`。各真实参与者用自己的工作副本和项目路径。`--blender` 可指定实际 Blender 可执行文件；省略文件参数用启动场景，仅显式 `--fixture` 才建测试面板、方块并保存实验文件。接收器不改名、增物体或保存业务文件，仅设临时输入配置、视口透视和窗口光标；IFC 加载、项目初始化由 Bonsai 启动器执行。用获授权的工作副本，不重启或接管用户正在编辑的实例。此路径需 `--enable-event-simulate`，会影响实例原生输入，故仅用于 task 自有临时实例。
4. A 查看自己的 `prepared.png`，核对 PID、窗口、文件、Perspective、`native-fullscreen.json`，记录截图实际控件坐标，再执行 `group.py ready --group "$GROUP"`。协调者再 grant B，B 重复准备。须核实两窗口在不同全屏桌面，不得左右分屏。只读 `spaces.swift` 可编译到技能 `.build/`，传入两个实际窗口 ID 核对 Space；系统接口不可用时用获授权的桌面观察核实，不猜测。
5. 两边 ready 后，协调者执行 `group.py formal --group "$GROUP"`，固定本轮真实 task、token、run、PID 出生身份、窗口及 session 绑定。须仍持准备租约才能准入；提前释放后不得继续准备或手写 formal。
6. formal 成功后立即执行 `desktop_queue.py release --lease-id "$LEASE" --outcome completed`，按返回的 `notify` 通知队首。此后后台权限查正式准入及固定绑定，无须旧租约有效。其他 task 可取得正常桌面队列；本组继续自己的输入、录屏和局部清理。此时禁止通过组权限 restore、全局输入或切换焦点，不得反复激活掩盖串扰。

## 正式录屏与输入

协调者启动有限时长服务，保留前台执行会话，不 detach：

```bash
python3 "$SKILL/experiments/cross_task/broker.py" --group "$GROUP" --seconds 1200
```

`ready` 仅表示服务就绪，尚未开始各参与者录屏；日常无须前台测试应用。`--foreground` 仅接受协调者当前仍持正常桌面租约的独立前台 session，不接受已释放旧租约的 session，不得为此保留准备租约。验证交接时，由取得新租约的真实 task 自己启动、录制、操作及清理前台探针，不将其 session 放入本组服务。任一参与者退出均不得杀掉共享服务。

各参与者独立控制自己的录屏：

```bash
python3 "$SKILL/experiments/cross_task/control.py" "$PARTICIPANT" start
python3 "$SKILL/experiments/cross_task/send.py" "$PARTICIPANT" --events "$EVENTS_JSON"
python3 "$SKILL/experiments/cross_task/control.py" "$PARTICIPANT" stop
```

`PARTICIPANT` 为真实 task enroll 生成的自己 run 目录下的 `participant.json`；不得复制他人回执、伪造环境或手写身份。`start` 等自己的首帧就绪才允许输入；`stop` 先排空、释放本窗口输入，校验本段录像；重启再调用 start。未录屏、旧 generation、已关闭成员及组外系统操作均被拒绝。

`EVENTS_JSON` 为有限的 Blender `Window.event_simulate` 事件数组，如移到已核实位置后 LEFTMOUSE PRESS/RELEASE。允许 A/C/V、RET、ESC、MOUSEMOVE、LEFTMOUSE、MIDDLEMOUSE 和滚轮；文本可用 A PRESS 的 unicode 字段输入，选择文本用已验证的 Ctrl+A，拒绝 oskey。Ctrl/Cmd 剪贴板快捷键、右键菜单、Tab/F3、打开/保存、新窗口等未验证路径不得按并行成功处理。

坐标用 Blender 窗口内部左下角像素，**不是** `desktop.py` 的归一化屏幕坐标。按最新截图宽高及实际 Retina 比例换算，翻转 y。先对本次目标做短录制可逆探针，观察真实 UI 结果后再正式验收。彩色 A/B 是 [辅助标注](blender-cursor.md)，非系统鼠标。

每批检查自己的 `state.json`、`events.jsonl`、`lifecycle.jsonl`；业务值以真实画面为准。正式阶段不得切回前台截图；需看结果时停止自己的片段，从自己的完整录像抽帧，另一方继续录制。VFR 取帧先按 `fps=30` 正规化再定位，不将稀疏帧误判为卡住。新加载文件、窗口变化或异常会使原绑定失效，须停止并重新串行准备，不放宽检查或自动转发旧动作。

## 各自清理和协调者收尾

参与者完成必要的结果/持久化核对，确认可关闭临时实例后：

```bash
python3 "$SKILL/experiments/cross_task/control.py" "$PARTICIPANT" stop
python3 "$SKILL/scripts/desktop.py" close --isolation-group "$GROUP" --session "$SESSION"
python3 "$SKILL/experiments/cross_task/group.py" closed --group "$GROUP"
```

已 stop 的片段不重复 stop。失败时保留失败结果及原片，必要时用 scoped `collect` 收集已停止的失败录制，不改报成功；无法确认输入排空/录制结束时，保留本组实例与证据并报告，不以申请或占住桌面队列代替局部清理。准备阶段异常且仍可能占用前台时，按普通队列规则保留自己的准备租约。准备失败且未 bind 时，参照原生工具引用，用自己的真实 launch.json 清理。

协调者确认双方实际 task 状态、各自日志/原片和归属关闭后：

```bash
python3 "$SKILL/experiments/cross_task/shutdown.py" "$GROUP"
python3 "$SKILL/experiments/cross_task/group.py" finish --group "$GROUP"
```

须先完成 shutdown 再 finish；服务未完成时 finish 拒绝。服务失败结束时，核实进程退出后可关闭组，但保留 `capture_outcome: failed` 及原失败日志，不算验收通过。此处不再释放准备租约，不改其他 task 队列状态。独立前台验证实例由持其当前正常租约的 task 用 `desktop.py stop/close` 收集、关闭，再释放自己的租约并通知交接。共享服务失效、系统休眠及未验证操作不在“互不干扰”保证内。

## 验证边界与素材

2026-09-23 r3 实验用两个真实 Codex task、不同全屏 Space 及各自实例。A/B 实际输入批次重叠约 62.9 秒；双方停录/重录时，另一方输入与帧数持续增加；A task 真正结束后 B 再完成三组操作。原片严格解码、独立交叉核对通过。前台为自动化原生输入探针，非真人；正式期间焦点、修饰键和剪贴板修订号无干扰。

证据仅证明此接入方式的受限操作，不推广到所有编辑器、保存弹窗或全部 Blender 插件。`run_trial.py`、`audit.py`、前台探针及固定 70 秒剪辑脚本仅用于复跑该实验，不作日常业务录屏模板；日常剪辑依自己的实际操作记录和最终成片时间映射。实验顺序回放的同期素材须明确标注，避免误认为两边轮流操作。

发布接入检查另验证两个 task 各自以 `--blend` 保留场景启动、无前台探针的服务、原生 Transform X 输入与透视旋转、各自停录/重录/关闭及源文件散列不变。实际操作时段未重叠，不作新并行证据；并行与前台共用仍依据上述 r3 完整实验。

2026-09-24 队列解耦复测在正式输入前释放协调者准备租约；真实 B task 正常取得新租约，独立操作、录制前台探针；A/B 后台实际输入批次仍重叠约 62.8 秒。双方停录/重录、A task 结束后 B 再操作、后台组收尾不改 B 新租约均通过，五份原片严格解码通过。前台为自动化探针，非真人；此测试证明准备租约与后台生命周期分开，不代表任意 Blender 操作均可无焦点执行。

2026-09-26 单任务入口复测仅用当前一个真实 task：准备准入后释放队列，连续 194.8 秒完成 36 轮文字、数值、开关、按钮及透视旋转；原片 2816 帧严格解码通过，651 次前台采样均非该 Blender 实例。前台应用与鼠标曾变化；本轮证明后台持续运行，不声称前台始终静止。录制启动中断后 collect 保留失败结论；重新 start 后操作通过并正常关闭。全局安装版另以 `--blend` 保留场景启动，真实 Transform X 依次为 250 mm、-250 mm、0 mm；透视旋转通过、源文件散列不变。此轮未重做双任务重叠实验，保证仍限于上述历史证据及权限回归；另存为、独立文件对话框和未支持快捷键仍走原生串行流程。

同轮仓库、全局安装版均通过 98 项自动化测试及技能结构校验。新增覆盖单任务归属、跨任务拒绝、释放准备队列后继续、启动中断收集、关闭回执恢复和失败服务收尾；自动化测试用隔离状态，不替代上述真实界面证据。

同日 IFC 接入复测复用实际项目初始化脚本及 IFC 副本，未转换或保存 `.blend`。后台真实界面完成配置展开/关闭且保持对象 GlobalId、从资产卡拖入一个 IFC 对象、打开平面和立面图、平面图滚轮缩放及中键平移，非脚本设置业务结果。所测操作区间 161 次前台采样均为独立测试应用，剪贴板修订号及修饰键状态未变。全局安装版另启 IFC 新实例，重复配置展开/关闭通过。源项目脚本、源 IFC 及测试 IFC 文件散列均未变；实例改动仅留在明确可丢弃的内存副本，两次实例与录屏服务均正常关闭。本轮不证明保存、所有插件或全部视图快捷键；一次侧视图坐标探针未打开图纸，不计通过。

IFC 候选、全局安装版均通过 106 项 Python 测试、2 项 Bun 测试。新增检查 IFC 参数及回执、项目脚本与真实标题转发、loader 先于输入接收器、半行日志、明确未启动的清理及启动后异常保留不确定回执。
