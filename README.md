# vibe_ampere

基于 Codex Skill 的 HOTONE Ampero II Stomp 音色 Agent 与安全本地控制层。

用户可以直接用自然语言描述目标音色，例如“更温暖”“减少刺耳感”“做一个低增益清音”，Codex 负责理解意图、查询官方编辑器随附的真实算法目录、生成可审阅的参数方案，并在用户明确确认后调用设备控制层。项目不再额外实现一套聊天界面，也不提供功能重复的通用 `amperoctl.exe`；用户入口是 `$ampero-tone` Skill，Python CLI 和 Dart bridge 都是内部、可测试的执行边界。

## 当前状态

- 自动发现本机安装的 Ampero II 官方编辑器、`HTUSBTools.dll` 和最新算法目录。
- 通过厂商 DLL 枚举 Ampero II Stomp 的 MIDI 输入/输出端口。
- 通过 Dart NativePort bridge 建立连接，兼容官方 Flutter 编辑器所依赖的回调模型。
- 读取当前 Scene 和完整当前预设，包括预设信息、Scene 名称、槽位顺序、模型、启用状态和可选参数值。
- 根据官方算法目录解析效果器、模型、参数名、参数 ID 和合法范围，不让模型编造协议标识符。
- 支持计划校验、精确预览、执行确认、写前读取、命令白名单、变更日志和回滚。
- 原生调用运行在独立子进程中；扫描最多等待 10 秒，快照最多等待 30 秒，超时后强制终止，避免 Codex 会话被 DLL 永久卡住。
- 包含 Python 单元测试、Dart 静态分析、Skill 校验和可重复执行的 bridge 构建脚本。

2026 年 7 月 18 日已在真实连接的 Ampero II Stomp 上完成只读验证：设备报告当前预设为 `Empty`，当前 Scene ID 为 `0`，共 3 个 Scene 和 12 个空槽位。尚未对真实硬件执行模型/参数写入、预设保存/删除、固件操作、恢复出厂或全局输出修改。

## 方案结构

```text
Codex conversation
       |
       v
ampero-tone Skill       自然语言工作流、方案格式和安全策略
       |
       v
Python control layer    目录查询、校验、预览、快照、日志和回滚
       |
       v
Dart FFI bridge         NativePort 注册、DLL timer pump、请求/响应
       |
       v
Ampero II Stomp
```

主要目录：

- `skills/ampero-tone/`：可安装到 Codex 的 Skill。
- `src/ampero_control/`：确定性的 Python 控制层。
- `bridge/`：Dart FFI bridge 源码。
- `examples/`：Schema version 1 音色计划示例。
- `docs/`：架构、协议、安全和开发说明。
- `tests/`：目录、协议、预设解析、控制器和 watchdog 测试。

## 环境要求

- Windows x64。
- Python 3.9 或更高版本，必须为 x64。
- 已安装官方 Ampero II Editor。
- 真实设备操作时通过 USB 连接 Ampero II Stomp。
- 构建 bridge 时需要 Dart SDK；运行已编译 bridge 时不需要系统级 Dart 环境。

本项目不会提交或重新分发官方 `HTUSBTools.dll`、算法目录、Dart SDK 或生成的 bridge 可执行文件。

## 快速开始

在项目目录打开 PowerShell：

```powershell
cd E:\vibe_ampere

$python = if ($env:AMPERO_PYTHON) {
    $env:AMPERO_PYTHON
} else {
    (Get-Command python).Source
}

& $python .\skills\ampero-tone\scripts\ampero.py --json doctor --scan
& $python .\skills\ampero-tone\scripts\ampero.py --json device snapshot --include-parameters
& $python .\skills\ampero-tone\scripts\ampero.py --json catalog search "clean" --category AMP
& $python .\skills\ampero-tone\scripts\ampero.py --json plan preview .\examples\clear-rhythm.plan.json
```

硬件访问应通过 Skill 自带的 `scripts/ampero.py` 包装器执行。包装器会在独立 worker 中运行控制层，并提供强制超时；不要直接对厂商 DLL 拼接命令或发送未知地址。

## 安装 Codex Skill

```powershell
.\scripts\install-skill.ps1 -Force
```

脚本会把 Skill 安装到 `$CODEX_HOME/skills/ampero-tone`，并设置用户环境变量 `VIBE_AMPERO_ROOT`。安装后重启 Codex。

可以这样对话：

- “使用 `$ampero-tone` 执行 doctor 和只读快照，不要修改参数。”
- “搜索适合单线圈的 clean amp，并展示真实参数范围。”
- “根据当前快照设计更清晰、低增益的节奏音色，只生成并预览方案。”
- “把方案的效果器、槽位和参数差异列出来，先不要应用。”
- “我确认应用刚才完整预览过的方案。”

## 安全工作流

1. 执行 `doctor --scan`，确认 DLL、bridge、设备端口和官方编辑器状态。
2. 执行只读 `device snapshot`，未知或失败的读取不能靠猜测补齐。
3. 查询本机官方算法目录，生成 Schema version 1 JSON 计划。
4. 运行 `plan validate` 和 `plan preview`。
5. 向用户展示精确效果器、槽位和参数差异。
6. 只有在用户明确批准完整预览后，才允许执行：

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan apply .\path\tone.plan.json --execute --confirm APPLY
```

执行成功后保留返回的 journal。需要回滚时仍须单独确认：

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan rollback .\path\change.journal.json --execute --confirm ROLLBACK
```

当前版本只修改 live edit buffer，不提供预设保存/删除、固件、bootloader、恢复出厂或全局输出命令。

## 开发与验证

运行 Python 测试：

```powershell
.\scripts\test.ps1
```

Python 不在默认位置时，可以设置 `AMPERO_PYTHON`，或显式传入：

```powershell
.\scripts\test.ps1 -PythonExecutable C:\Path\To\python.exe
```

构建 Dart bridge：

```powershell
.\scripts\build-bridge.ps1 -DartExe C:\Path\To\dart.exe
```

默认输出为 `.tools/ampero_bridge.exe`；`.tools/` 已被 Git 忽略。

进一步说明：

- `docs/architecture.md`：模块划分、transport 边界和产品形态。
- `docs/protocol.md`：已实现的 DLL 与消息协议兼容子集。
- `docs/safety.md`：硬件写入和回滚安全约束。
- `docs/development.md`：开发、测试和 Skill 安装命令。
