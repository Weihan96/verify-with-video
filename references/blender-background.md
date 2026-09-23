# Blender 后台并行输入与录屏

适用于 macOS、Blender 4.5.3 LTS、两个真实 Codex task 各自拥有的临时验收实例。协调 task 保留原全局队列凭据，串行准备两个不同 macOS Space 中的原生全屏窗口；正式阶段窗口内部事件与各自录屏可以同时运行。用户可继续使用前台其他应用。它不是多个系统鼠标，也不是所有 Blender 功能的通用无焦点驱动。

代码保留在 `experiments/cross_task/` 以维持已测试的导入和接入路径，随技能安装提供。不要使用历史 `experiments/isolation/` 的同会话原型代替此入口。以下 `SKILL` 为当前安装目录，`GROUP`、`RUN`、真实 task ID 和租约均使用本次工具返回值，不能照抄旧证据。

验收若必须保存、重开文件、操作独立弹窗或使用未支持快捷键，应在开始时选择普通原生串行流程。现有并行实例不支持中途切回原生输入；途中发现此需求时停止自己的输入与录制，保留未保存实例并报告，不能以关闭或重新打开丢弃草稿来冒充串行保存。只有明确为可丢弃的工作副本才可正常关闭。

## 建组和准备

1. 协调者按 [桌面队列](desktop-queue.md) 取得凭据。复用两个已明确参与的真实 task；用户要求新建 task 时用任务工具创建，不以同一会话的两个脚本冒充。组内固定两个参与者，协调者是第三个 task；未提供这样的任务安排时，不声称任意独立 task 已自动并行。
已入组的参与者不再自行申请全局队列，避免等待自己的协调者。
2. 协调者建组并授权 A 准备：

   ```bash
   python3 "$SKILL/experiments/cross_task/group.py" create --lease "$LEASE" --run "$RUN" --member "A=$TASK_A" --member "B=$TASK_B"
   python3 "$SKILL/experiments/cross_task/group.py" grant --group "$GROUP" --label A
   ```

3. A 在自己的真实 task 环境执行：

   ```bash
   python3 "$SKILL/experiments/cross_task/prepare.py" "$GROUP" --blend "$WORKFILE"
   ```

   `--blender` 可指定实际 Blender 可执行文件。省略 `--blend` 使用当前启动场景；只有显式 `--fixture` 才创建测试面板、方块并保存实验文件。业务模式不改名、增物体或保存工作文件，仅设置临时输入配置、视口透视和窗口光标。使用已获授权的工作副本，不重启或接管用户正在编辑的实例。此启动路径需要 `--enable-event-simulate`，会影响该实例原生输入，因此仅用于 task 自己的临时实例；领域启动器必须支持这些参数及真实归属回执，否则用本入口并明确领域功能未验证。
4. A 查看自己的 `prepared.png`，核对 PID、窗口、文件、Perspective、`native-fullscreen.json`，记录本截图实际控件坐标，然后执行 `group.py ready --group "$GROUP"`。协调者再 grant B，由 B 重复准备。必须核实两个窗口位于不同全屏桌面；不能左右分屏。只读的 `spaces.swift` 可编译到技能 `.build/` 并传入两个实际窗口 ID 核对 Space；系统接口不可用时以授权的桌面观察核实，不猜测。
5. 两边 ready 后协调者执行 `group.py formal --group "$GROUP"`。这一阶段禁止 restore、全局输入或切换焦点；不能通过反复激活掩盖串扰。

## 正式录屏与输入

协调者启动有限时长服务，保留前台执行会话，不 detach：

```bash
python3 "$SKILL/experiments/cross_task/broker.py" --group "$GROUP" --seconds 1200
```

`ready` 只说明服务就绪，还没有开始各参与者的录屏。`--foreground` 是验证前台共用时才使用的可选根 task 窗口 session，日常使用不需要前台测试应用。任一参与者退出都不能杀掉此共享服务。

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

已经 stop 的片段不重复 stop。失败时保留失败结果和原片，必要时用 scoped `collect` 收集已停止的失败录制，不能把它改报成功；无法确认输入排空/录制结束时保留协调占用并报告。准备失败且未 bind 时用自己的真实 launch.json 清理，参照原生工具引用。

协调者确认双方实际 task 状态、各自日志/原片和归属关闭后：

```bash
python3 "$SKILL/experiments/cross_task/shutdown.py" "$GROUP"
python3 "$SKILL/experiments/cross_task/group.py" finish --group "$GROUP"
python3 "$SKILL/scripts/desktop_queue.py" release --lease-id "$LEASE" --outcome completed
```

有前台验证实例时沿用 `desktop.py stop/close` 收集并关闭自己的前台实例，再 finish/release。保留队列通知交接规则。共享服务失效、系统休眠及未验证操作不在“互不干扰”保证内。

## 验证边界与素材

2026-09-23 的 r3 实验使用两个真实 Codex task、不同全屏 Space 和各自实例。A/B 实际输入批次重叠约 62.9 秒，双方停录/重录时另一方输入与帧数持续增加；A task 真正结束后 B 再完成三组操作。原片严格解码和独立交叉核对通过。前台采用自动化原生输入探针，并非真人，正式期间焦点、修饰键和剪贴板修订号无干扰。

这些证据证明该接入方式的受限操作，不能推广到所有编辑器、保存弹窗或全部 Blender 插件。`run_trial.py`、`audit.py`、前台探针与固定 70 秒剪辑脚本只用于复跑该实验，不作为日常业务录屏模板；日常剪辑按自己的实际操作记录和最终成片时间映射进行。实验顺序回放的同期素材须明确标注，不能让观众误以为两边轮流操作。

发布接入检查另行验证了两个 task 各自以 `--blend` 保留场景启动、无前台探针的服务、原生 Transform X 输入与透视旋转、各自停录/重录/关闭及源文件散列不变。该接入检查的实际操作时段未重叠，不作为新的并行证据；并行与前台共用依据上述 r3 完整实验。
