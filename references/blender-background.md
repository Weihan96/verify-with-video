# Blender 后台输入与录屏

适用于 macOS、Blender 4.5.3 LTS 和真实 Codex task 自己拥有的临时验收实例。单个任务可独立准备、准入、后台输入和录屏；已有多任务安排时也可由协调者串行准备两个不同 macOS Space 中的原生全屏窗口。正式准入后立即释放准备凭据，窗口内部事件与录屏继续运行，其他 task 可正常取得桌面队列。用户可继续使用前台其他应用。它不是多个系统鼠标，也不是所有 Blender 功能的通用无焦点驱动。

代码保留在 `experiments/cross_task/` 以维持已测试的导入和接入路径，随技能安装提供。不要使用历史 `experiments/isolation/` 的同会话原型代替此入口。以下 `SKILL` 为当前安装目录，`GROUP`、`RUN`、真实 task ID 和租约均使用本次工具返回值，不能照抄旧证据。

验收若必须保存、重开文件、操作独立弹窗或使用未支持快捷键，应在开始时选择普通原生串行流程。现有并行实例不支持中途切回原生输入；途中发现此需求时停止自己的输入与录制，保留未保存实例并报告，不能以关闭或重新打开丢弃草稿来冒充串行保存。只有明确为可丢弃的工作副本才可正常关闭。

## 单任务入口（普通 Blender 后台验收默认使用）

`BG` 为本技能 `scripts/blender_background.py` 的绝对路径。使用当前真实 `CODEX_THREAD_ID`，不创建辅助任务、不伪造其他身份。先按桌面队列取得本次 `LEASE`，选择新的绝对路径 `RUN`：

```bash
python3 "$BG" prepare --lease "$LEASE" --run "$RUN" --blend "$WORKFILE"
```

`--blend` 打开已获授权的工作副本；省略时保留启动场景。只有明确测试临时控件时才用 `--fixture`。可用 `--blender` 指定可执行文件。

IFC/Bonsai 不必先另存 `.blend`。先读已安装的 `bonsai-launcher` 技能，使用实际项目工作目录、获授权的 IFC 副本与项目已有初始化脚本：

```bash
python3 "$BG" prepare --lease "$LEASE" --run "$RUN" \
  --ifc "$IFC_COPY" --worktree "$PROJECT" \
  --prepare-script "$PROJECT_BOOTSTRAP" --task-title "$ACTUAL_TASK_TITLE"
```

不需要项目插件时省略 `--prepare-script`。`--blend`、`--ifc`、`--fixture` 互斥。`--task-title` 取当前任务实际标题；不提供时不设置标题，保留启动器默认场景名。默认复用 `$CODEX_HOME/skills/bonsai-launcher/scripts/bonsai-launcher.ts`（未设置 CODEX_HOME 时为 `~/.codex`）；不同安装位置通过 `--bonsai-launcher` 指定，不为此更改 CODEX_HOME。该依赖不随本技能打包；缺失时在建组前报错。

适配器复用启动器的任务锁、IFC loader、`--no-save` 与真实归属回执，加入后台输入参数并在 IFC/项目初始化后启动输入接收器。接收器保留业务场景。准备等待 IFC 成功回执和接收器同时就绪，核对源文件散列、PID、未保存 `.blend` 和警告状态；默认最多 120 秒，可用 `--prepare-timeout` 调整至 600 秒。初始化失败或超时不算成功，保留自己的启动凭据供清理。项目初始化脚本仍须先检查其行为；它若要求外部窗口、未授权写入或改变文件，应先解决该具体问题。

已有普通实例不会自动变为后台实例。启动器发现冲突时保留原实例，不能加替换参数或伪造身份绕过归属锁；检查现有实例/草稿后再决定，不能只因现有窗口失焦要求用户“现在录”。IFC 路径不覆盖未保存场景，也不新增保存、文件对话框等支持。

计划生成失败、Bun 子进程无法创建或明确返回 `existing` 时，删除的仅是本次未启动的占位回执，随后可正常关闭空准备组。进入启动器后报错、输出损坏或通信中断仍属启动状态不确定：保留占位和错误，核对启动器状态、任务锁 owner 与日志后再处理；不把一次查不到 PID 当作未启动证明，不删锁或猜测 PID。锁冲突若未提供结构化未启动回执，同样按不确定状态保留。

脚本完成单任务建组、授权和启动后返回截图；查看 `RUN/A/prepared.png`（IFC 另有 `RUN/A/ifc-ready.json`），核对实际文件、窗口、Perspective、项目插件与控件坐标，再执行：

```bash
python3 "$BG" admit --run "$RUN"
```

`admit` 固定同一任务的实例归属，并立即释放准备租约；按输出 `handoff.notify` 发送队首通知、成功后登记。准备或准入失败时保留 run、启动回执和准备租约，检查后清理自己的实例；不能提前释放后强行准入。`admit` 可用于完成准入后中断的交接。

启动有限时长服务，保留工具执行 session，不 detach；它输出 `ready` 后再开始录制：

```bash
python3 "$BG" serve --run "$RUN" --seconds 1200
python3 "$BG" start --run "$RUN"
python3 "$BG" send --run "$RUN" --events "$EVENTS_JSON"
python3 "$BG" stop --run "$RUN"
```

`serve` 保持运行，其他命令在独立工具调用中执行。`start` 等首帧，`stop` 排空输入并严格解码本段；需要继续则再次 `start`。先短片确认实际控件响应，再正式操作。支持事件、坐标、日志和抽帧方式见下节，与多任务使用同一实现。正式阶段无需前台焦点；不要因 Blender 不在前台而停录或向用户索要“现在录”。本入口不自动切换到原生输入。

确认临时场景可以关闭，先 `stop`（失败录像用 `collect` 保留失败信息），再执行：

```bash
python3 "$BG" close --run "$RUN"
```

`close` 关闭本任务实例、完成服务收尾和组关闭；不会替你保存，也不会丢弃活跃录像或改动其他任务的队列。准备失败时也可在仍持有准备租约的情况下 `close`，成功后另行 release 准备租约并交接。启动录制中断时，先 `collect` 收集本次待启动录制再重试；未就绪的录制不能授权输入。失败后的 `status --run "$RUN"` 可查看保留状态。资源已清理不代表录像成功：服务有失败日志时，关闭结果保留 `capture_outcome: failed`。源码继续复用 `experiments/cross_task/`，单任务和多任务的 token、PID、窗口、首帧、排空与录制校验一致。

## 多任务建组和准备

仅在已有两个真实参与任务的并行验收安排时使用本节；普通单任务使用上面的入口。


1. 协调者按 [桌面队列](desktop-queue.md) 取得凭据。复用两个已明确参与的真实 task；用户要求新建 task 时用任务工具创建，不以同一会话的两个脚本冒充。此多任务入口固定两个参与者，协调者是第三个 task；不为单任务录屏创建这个安排。
参与者的组内后台操作不申请全局队列。若另有独立的前台应用工作，仍按普通流程申请自己的队列凭据，不能复用后台权限。
2. 协调者建组并授权 A 准备：

   ```bash
   python3 "$SKILL/experiments/cross_task/group.py" create --lease "$LEASE" --run "$RUN" --member "A=$TASK_A" --member "B=$TASK_B"
   python3 "$SKILL/experiments/cross_task/group.py" grant --group "$GROUP" --label A
   ```

3. A 在自己的真实 task 环境执行：

   ```bash
   python3 "$SKILL/experiments/cross_task/prepare.py" "$GROUP" --blend "$WORKFILE"
   ```

   与单任务入口共用场景参数；IFC 可将 `--blend` 换成 `--ifc`、`--worktree` 和可选的 `--prepare-script`，每个真实参与者使用自己的工作副本和项目路径。`--blender` 可指定实际 Blender 可执行文件。省略文件参数使用启动场景；只有显式 `--fixture` 才创建测试面板、方块并保存实验文件。输入接收器不改名、增物体或保存业务文件，仅设置临时输入配置、视口透视和窗口光标；IFC 加载和项目初始化另由 Bonsai 启动器执行。使用已获授权的工作副本，不重启或接管用户正在编辑的实例。此启动路径需要 `--enable-event-simulate`，会影响该实例原生输入，因此仅用于 task 自己的临时实例。
4. A 查看自己的 `prepared.png`，核对 PID、窗口、文件、Perspective、`native-fullscreen.json`，记录本截图实际控件坐标，然后执行 `group.py ready --group "$GROUP"`。协调者再 grant B，由 B 重复准备。必须核实两个窗口位于不同全屏桌面；不能左右分屏。只读的 `spaces.swift` 可编译到技能 `.build/` 并传入两个实际窗口 ID 核对 Space；系统接口不可用时以授权的桌面观察核实，不猜测。
5. 两边 ready 后协调者执行 `group.py formal --group "$GROUP"`，固定本轮真实 task、token、run、PID 出生身份、窗口与 session 绑定。只有仍持有准备租约时才能完成准入；提前释放后不能继续准备或手写 formal。
6. formal 成功后，立即执行 `desktop_queue.py release --lease-id "$LEASE" --outcome completed`，按返回的 `notify` 完成队首通知。后台权限此后检查正式准入和固定绑定，不要求旧租约仍有效。其他 task 可取得正常桌面队列；本组继续自己的输入、录屏和局部清理。此阶段禁止通过组权限 restore、全局输入或切换焦点；不能反复激活掩盖串扰。

## 正式录屏与输入

协调者启动有限时长服务，保留前台执行会话，不 detach：

```bash
python3 "$SKILL/experiments/cross_task/broker.py" --group "$GROUP" --seconds 1200
```

`ready` 只说明服务就绪，还没有开始各参与者的录屏。日常使用不需要前台测试应用。`--foreground` 仅接受协调者当前仍有正常桌面租约的独立前台 session，不能传入已释放旧租约的 session；也不能为了使用它而保留准备租约。验证队列交接时，让取得新租约的真实 task 自己启动、录制、操作和清理前台探针，不把其 session 塞入本组服务。任一参与者退出都不能杀掉此共享服务。

各参与者独立控制自己的录屏：

```bash
python3 "$SKILL/experiments/cross_task/control.py" "$PARTICIPANT" start
python3 "$SKILL/experiments/cross_task/send.py" "$PARTICIPANT" --events "$EVENTS_JSON"
python3 "$SKILL/experiments/cross_task/control.py" "$PARTICIPANT" stop
```

`PARTICIPANT` 是自己 run 目录中的 `participant.json`，由真实 task enroll 产生；不能复制别人回执、伪造环境或手写身份。`start` 等自己首帧就绪后才允许输入，`stop` 先排空并释放本窗口输入、校验本段录像；重启再调用 start。未录屏、旧 generation、已关闭成员及组外系统操作会被拒绝。

`EVENTS_JSON` 是有限的 Blender `Window.event_simulate` 事件数组，例如移动到已核实位置后 LEFTMOUSE PRESS/RELEASE。允许 A/C/V、RET、ESC、MOUSEMOVE、LEFTMOUSE、MIDDLEMOUSE 和滚轮；文本可通过 A PRESS 的 unicode 字段输入，选择文本用已验证的 Ctrl+A，拒绝 oskey。Ctrl/Cmd 剪贴板快捷键、右键菜单、Tab/F3、打开/保存、新窗口等未验证路径不能按并行成功处理。

坐标使用 Blender 窗口内部左下角像素，**不是** `desktop.py` 的归一化屏幕坐标。按最新截图宽高和实际 Retina 比例换算；y 要翻转。先用本次目标做短录制可逆探针，观察真实 UI 结果后再正式验收。彩色 A/B 是 [辅助标注](blender-cursor.md)，不代表系统鼠标。

每批检查自己的 `state.json`、`events.jsonl`、`lifecycle.jsonl`；业务值以真实画面为准。正式阶段不能切回前台截图；需要看结果时停止自己的一个片段并从自己的完整录像抽帧，另一方继续录制。VFR 取帧先按 `fps=30` 正规化再定位，不能将稀疏帧错误解读为卡住。新加载文件、窗口变化或异常会使原绑定失效，应停止并重新串行准备；不要放宽检查或自动转发旧动作。

## 各自清理和协调者收尾

参与者完成必要的结果/持久化核对，确认可以关闭临时实例后：

```bash
python3 "$SKILL/experiments/cross_task/control.py" "$PARTICIPANT" stop
python3 "$SKILL/scripts/desktop.py" close --isolation-group "$GROUP" --session "$SESSION"
python3 "$SKILL/experiments/cross_task/group.py" closed --group "$GROUP"
```

已经 stop 的片段不重复 stop。失败时保留失败结果和原片，必要时用 scoped `collect` 收集已停止的失败录制，不能把它改报成功；无法确认输入排空/录制结束时保留本组实例与证据并报告，不申请或占住桌面队列来代替局部清理。准备阶段发生异常且仍可能占用前台时，按普通队列规则保留自己的准备租约。准备失败且未 bind 时用自己的真实 launch.json 清理，参照原生工具引用。

协调者确认双方实际 task 状态、各自日志/原片和归属关闭后：

```bash
python3 "$SKILL/experiments/cross_task/shutdown.py" "$GROUP"
python3 "$SKILL/experiments/cross_task/group.py" finish --group "$GROUP"
```

必须先 shutdown 完成再 finish，服务尚未完成时 finish 会拒绝。服务以失败结束时，核实进程退出后可完成组关闭，但保留 `capture_outcome: failed` 和原失败日志，不能当作验收通过。此处不再释放准备租约，也不改变其他 task 的队列状态。有独立前台验证实例时，由持有其当前正常租约的 task 用 `desktop.py stop/close` 收集和关闭，再释放它自己的租约并完成通知交接。共享服务失效、系统休眠及未验证操作不在“互不干扰”保证内。

## 验证边界与素材

2026-09-23 的 r3 实验使用两个真实 Codex task、不同全屏 Space 和各自实例。A/B 实际输入批次重叠约 62.9 秒，双方停录/重录时另一方输入与帧数持续增加；A task 真正结束后 B 再完成三组操作。原片严格解码和独立交叉核对通过。前台采用自动化原生输入探针，并非真人，正式期间焦点、修饰键和剪贴板修订号无干扰。

这些证据证明该接入方式的受限操作，不能推广到所有编辑器、保存弹窗或全部 Blender 插件。`run_trial.py`、`audit.py`、前台探针与固定 70 秒剪辑脚本只用于复跑该实验，不作为日常业务录屏模板；日常剪辑按自己的实际操作记录和最终成片时间映射进行。实验顺序回放的同期素材须明确标注，不能让观众误以为两边轮流操作。

发布接入检查另行验证了两个 task 各自以 `--blend` 保留场景启动、无前台探针的服务、原生 Transform X 输入与透视旋转、各自停录/重录/关闭及源文件散列不变。该接入检查的实际操作时段未重叠，不作为新的并行证据；并行与前台共用依据上述 r3 完整实验。

2026-09-24 的队列解耦复测在正式输入前释放协调者准备租约，真实 B task 正常取得新租约，独立操作并录制前台探针；A/B 后台实际输入批次仍重叠约 62.8 秒。双方停录/重录、A task 结束后 B 再操作、后台组收尾不改变 B 新租约均通过，五份原片严格解码通过。前台为自动化探针，非真人；该测试证明准备租约与后台生命周期已经分开，不意味着任意 Blender 操作均可无焦点执行。


2026-09-26 的单任务入口复测仅使用当前一个真实 task：准备准入后释放队列，连续 194.8 秒完成 36 轮文字、数值、开关、按钮与透视旋转；原片 2816 帧严格解码通过，651 次前台采样均不是该 Blender 实例。前台应用与鼠标曾变化，因此该轮证明后台持续运行，不另声称前台始终静止。录制启动中断后 collect 保留失败结论，重新 start 后操作通过，正常关闭完成。全局安装版另以 `--blend` 保留场景启动，真实 Transform X 依次为 250 mm、-250 mm、0 mm，透视旋转通过、源文件散列不变。此轮未重做双任务重叠实验，其保证仍以上述历史证据及权限回归为边界；另存为、独立文件对话框和未支持快捷键仍走原生串行流程。

同轮仓库与全局安装版均通过 98 项自动化测试及技能结构校验。新增覆盖单任务归属、跨任务拒绝、释放准备队列后继续、启动中断收集、关闭回执恢复和失败服务收尾；自动化测试使用隔离状态，不代替上述真实界面证据。

同日 IFC 接入复测复用了实际项目初始化脚本和 IFC 副本，未转换或保存 `.blend`。后台真实界面完成配置展开/关闭且保持对象 GlobalId、从资产卡拖入一个 IFC 对象、打开平面和立面图、平面图滚轮缩放及中键平移；不是通过脚本设置业务结果。所测操作区间的 161 次前台采样均为独立测试应用，剪贴板修订号及修饰键状态未变。全局安装版另行启动新的 IFC 实例，重复配置展开/关闭通过。源项目脚本、源 IFC 与测试 IFC 文件散列均未变，实例改动仅留在明确可丢弃的内存副本，两次实例与录屏服务正常关闭。该轮不证明保存、所有插件或全部视图快捷键；侧视图的一次坐标探针没有打开图纸，不计作通过。

IFC 候选与全局安装版均通过 106 项 Python 测试、2 项 Bun 测试。新增检查 IFC 参数和回执、项目脚本与真实标题转发、loader 先于输入接收器、半行日志、明确未启动的清理，以及启动后异常保留不确定回执。
