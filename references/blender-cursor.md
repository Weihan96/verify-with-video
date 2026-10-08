# Blender 输入光标标记

Blender 模拟输入录屏可用 `+ A` / `+ B` 彩色标记显示操作位置。这是本技能绘制的辅助标注，非 Blender 自带或 macOS 系统光标；仅说明输入驱动报告的坐标，不证明控件响应。视频标题或旁白首次出现时说明“彩色字母为模拟输入位置标记”。

## 适用范围

- `scripts/blender_cursor.py` 是 Blender 内部绘制模块，针对 Blender 4.5.3 LTS 验证；仅画 `VIEW_3D` 主视口及 N 侧栏。其他编辑器、独立窗口、操作系统对话框及弹窗覆盖区不保证显示，先短录屏检查目标步骤。
- 模块不发送输入、不监听系统鼠标；由已有输入驱动在成功投递事件后调用 `update`。未集成回调不得用静止标记冒充当前鼠标。原生桌面录制仍用真实系统光标，不默认替换。
- 本模块仅作可视化；窗口输入和独立录制用 [后台并行接入](blender-background.md)，仅准备阶段占桌面队列，正式准入后释放。`--enable-event-simulate` 抑制 Blender 普通原生输入，仅用于已授权的临时测试实例；不得为显示光标重启或改造用户建模会话。
- 每个标记绑定一个实际 Blender `Window`，每窗口最多一个。坐标为窗口内部、左下角原点的像素，与 `Window.event_simulate(x=..., y=...)` 一致；不得直传屏幕坐标、归一化截图坐标或假定固定 Retina 倍率。Retina 下 `Window.width/height` 可能为逻辑点，区域坐标才是绘制像素；模块按实际区域边界处理。

## 集成到已有输入驱动

代码在 Blender 主线程运行，路径按当前技能位置解析；`window` 来自已核对的任务目标，不得无条件选首个同名窗口。

```python
import importlib.util

spec = importlib.util.spec_from_file_location('video_cursor', cursor_script_path)
video_cursor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_cursor)
marker = video_cursor.enable(window, label='A')

# 每次使用同一份实际事件参数；投递失败时不更新标记。
window.event_simulate(**event_args)
marker.update(window, event_args['x'], event_args['y'])
```

A 默认橙色，其余标签默认黄色。标签可用 1–16 个可打印字符；可传 `color=(r, g, b, a)`（每项 0–1）、`size=17`（10–48）。标签仅区分实例，不暗示多个系统鼠标；保留实际界面变化作为成功依据。

## 生命周期

- 重复 `enable(window, ...)` 会清理同窗口旧标记，含同脚本另次导入所建标记；新对象首次 `update` 前不显示。
- `marker.hide()` 暂时隐藏，后续有效 `update` 可恢复；窗口外坐标也会隐藏。
- `marker.stop()` 移除自身绘制及文件加载回调，可重复调用。`video_cursor.disable_all()` 仅清理当前 Blender 进程内本模块标记，不操作系统鼠标。
- 打开文件或 Revert 前自动清理，旧对象随后拒绝更新。复核文件、窗口及透视状态后，显式 `enable` 创建新对象，不得自动转发旧动作到新窗口。
- 错误/过期窗口或非法坐标会报错；输入驱动应记录、停止本段操作并复核目标，不得吞错后把光标显示算作通过。
- 不写 Scene 属性、首选项或启动文件，不注册操作符、计时器或全局鼠标监听；退出 Blender 不留系统层光标。

## 发布前验证

自动测试覆盖窗口/区域隔离、重复导入启用、关闭及文件加载清理、越界/非法坐标、注册/绘制失败清理。真实 Blender 录屏还应确认 A/B 颜色、视口到侧栏移动、重复启用无重影、隐藏/停止后消失、重载后旧标记消失且重新启用正常，并查看实际操作结果。代码测试或旧原型视频不能替代修改后实现的界面验证。

## 已验证版本

2026-09-22 于 macOS / Blender 4.5.3 LTS 验证本模块：两个独立全屏 Space、两个实例各 147 个正式输入事件（另有一次准备移动），完成交叉拖动/文本输入、重复启用、隐藏、停止、重新启用、错误窗口拒绝、弹窗及 Revert 后清理和显式重绑。抽看原片确认显示/消失与日志一致。69 项仓库自动测试通过，其中 10 项针对本模块。

以上为光标模块早期验证；后续两个真实 task 的并行输入、录屏验证及使用边界见 [后台并行接入](blender-background.md)。操作系统全屏准备工具曾窗口匹配失败，最终用 Blender 自身全屏启动，在 Mission Control 确認独立 Space；光标模块不提供此桌面管理能力。
