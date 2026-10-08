# 共享桌面队列

队列协调同机录屏验收，不探测、获取或强制释放底层桌面资源，不能约束未参与本流程的会话。参与者须共用状态，不得另建队列绕过占用。

## 文件与身份

- 脚本：本技能 `scripts/desktop_queue.py`，用 `python3`、仅依赖标准库。POSIX `flock` 在进程退出时自动释放短时写入锁，适用于本地 macOS/Linux 文件系统。
- 默认状态目录：`${CODEX_HOME:-$HOME/.codex}/state/computer-use/`，独立于项目、worktree 和技能副本。同桌面会话须共用 CODEX_HOME，不得改此变量绕过队列。`--state-dir` 仅用于隔离测试。
- `queue.json`：`current` 为当前协调占用（含 `thread_id`、`ticket`、`lease_id`），空闲为 `null`；`waiting` 按取号顺序记录 `thread_id`、`ticket`、`requested_at`；`notification` 保存当前队首通知状态。
- `history.json`：`sessions` 按释放顺序保存每次协调占用的会话 ID、号码、凭据、申请/取得/释放时间及结果。此历史不证明实际界面操作或验收通过；撤销未用号码不计使用。
- `.write.lock` 仅在读写 JSON 时加锁，等待、验收时不持锁。文件留在原处，系统锁已释放，不得删文件“解锁”。`.transaction.json` 为中断恢复日志，下次命令在写入锁内重放同次提交，使队列与历史一致，不另分配使用权。
- 默认读 `CODEX_THREAD_ID`；缺失时从当前任务可信元数据取真实 ID，以 `--thread-id` 传入。不得猜测、用他人 ID 或把待创建任务临时 clientThreadId 当作 threadId；环境已有 ID 时拒绝不一致参数。

`QUEUE_TOOL` 为本技能 `scripts/desktop_queue.py` 实际绝对路径，执行前按当前安装位置设置；搬迁技能只改脚本路径，不改共享状态目录。所有命令返回 JSON，失败返回非零退出码，失败时禁止继续界面操作。

## 申请、等待、续用

```bash
python3 "$QUEUE_TOOL" request
```

- `result: acquired`：确认 `queue.current.thread_id` 是自己，保存 `lease_id`；重复申请返回原号码及凭据，不重复入队。
- `result: waiting`：告知用户号码、前方等待人数（`position - 1`）及当前使用会话；继续不占桌面的准备，再等线程通知。若保持本轮活跃，可用能被新消息打断的等待工具，每 30–60 秒休息后运行 `status`；不得连续试用共享桌面、创建后台常驻轮询进程或擅自定时唤醒。
- 队首未收到通知也可在 `status` 确认空闲后 `request` 接手；其他人留在原位，队首离线不自动跳过。停止等待须执行 `cancel`，不得遗留号码。
- 工具上下文恢复、收到通知或开始下一段界面操作前，检查本次凭据：

```bash
python3 "$QUEUE_TOOL" check --lease-id '<本次 lease_id>'
```

`check` 仅核对协调占用，不证明底层工具空闲。工具报告另一会话仍在使用时，保留自身协调位置、报告实际阻塞，等真实持有者释放；不得重新初始化/重置其工具、结束其进程、代释放资源或删队列记录。放弃本次验收时，确认自己未持实际工具，再 `release --outcome backend_busy` 并通知下一位；不得反复释放再申请争抢资源。

## 已准入 Blender 后台组

[Blender 后台流程](blender-background.md) 协调者仅在启动、全屏桌面准备及 formal 准入期间持有本队列；准入后立即 release 并通知下一位。之后固定实例的后台输入、录屏、局部清理用组权限，不持续占号或检查旧租约；关闭后台组不释放其他 task 的队列。独立前台操作仍须正常申请，不得用组权限调用系统输入。

## 结束与取消

先停止本次前台租约保护的录屏及待执行界面动作。已 formal 准入的后台 Blender 组按自身生命周期运行，不随独立前台租约释放而停止。有明确且仅针对自己的释放接口时调用；否则按工具文档结束本会话使用，不臆造接口、不用全局 reset 代替释放。随后执行：

```bash
python3 "$QUEUE_TOOL" release --lease-id '<本次 lease_id>'
```

错误或取消后用 `--outcome aborted` 清理。仅当前会话和匹配的 `lease_id` 可释放；重复释放同一凭据不重复写历史、不释放后续占用。旧清理动作不能释放同会话新一轮凭据。

尚在等待时退出：

```bash
python3 "$QUEUE_TOOL" cancel
```

仅能撤销自己；取消空闲队首会为新队首生成通知，使用者须走 `release`。崩溃后系统释放写入文件锁，协调占用/等待号码不自动过期；应由原会话恢复清理，无法恢复则报用户核实处理，不自行驱逐。

## 必须完成的通知交接

脚本持久保存待通知记录，不连接 Codex 内部服务；执行技能的会话调用线程消息工具。**打印 `notify` 不等于已发出通知。**

1. `release`、`cancel` 或后续检查返回非空 `notify` 时，以其 `arguments` 调用 `mcp__codex_app__send_message_to_thread`，目标为记录中的 `threadId`。保留队列通知 ID 及提醒文本，不带入前任务私有内容、不改对方模型、标题或原任务范围。
2. 工具明确成功后才登记通知 ID：

```bash
python3 "$QUEUE_TOOL" notified --notification-id '<notify.id>'
```

3. 工具不可用、失败或结果不确定时，不执行 `notified`，报告“协调占用已释放，队首通知尚未确认”，保留待通知记录；恢复后先读取：

```bash
python3 "$QUEUE_TOOL" notifications
```

按当前返回的 `notify` 重试，不缓存旧收件人反复发信。队首先自行接手/取消会使通知失效，旧回执不覆盖新通知。“发送成功、登记前中断”可导致同 ID 重复通知；收件人须检查当前任务仍需验收并复核队列，不得将每条通知当新任务再次取号。

消息工具向目标线程发送可见后续消息以唤醒它，仅用于真实交接；测试用隔离状态、模拟会话，不向其他真实线程发测试消息。

## 状态异常

```bash
python3 "$QUEUE_TOOL" status
```

写入锁忙时最多等 5 秒后退出，可稍后重试；禁止删锁或改占用。JSON 损坏、文件缺失或版本/顺序不一致时停止、保留证据，不作空队列重建。无 TTL、自动回收、插队、代释放、force 或 reset 命令。队列是自愿协调，不是身份认证或权限隔离系统。

兼容性：历史路径 `computer_use_queue.py` 仍为同一实现的入口；状态目录 `computer-use` 仅是历史标识，不代表调用内置界面工具。不得迁移或重建状态。
