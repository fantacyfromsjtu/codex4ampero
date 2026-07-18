# codex4ampero

**中文** | [English](#english)

`codex4ampero` 是一个面向 **HOTONE Ampero II Stomp** 的 Codex 原生音色 Agent 与安全本地控制层。

你可以直接告诉 Codex：

- “把这个音色调得更温暖、少一点刺耳感。”
- “联网调研某首歌的 Solo 音色，先给方案，不要直接写设备。”
- “将确认后的音色自动写入 A50-1，并生成保存预览。”
- “回滚刚才不满意的修改。”

Codex 负责理解目标、调研歌曲或艺人的音色背景、查询官方编辑器随附的真实算法目录、生成可审阅计划，并在经过明确确认后调用确定性的本地控制层。底层不会让语言模型直接构造任意设备消息。

> [!IMPORTANT]
> 本项目是独立的兼容性研究项目，不是 HOTONE 或 OpenAI 的官方产品。项目不会分发 HOTONE 编辑器、`HTUSBTools.dll`、官方算法目录、固件或预编译的厂商组件。

## 目录

- [核心功能](#核心功能)
- [项目状态与兼容性](#项目状态与兼容性)
- [工作原理](#工作原理)
- [环境要求](#环境要求)
- [安装](#安装)
- [使用 Codex Skill](#使用-codex-skill)
- [命令行使用](#命令行使用)
- [音色计划与保存流程](#音色计划与保存流程)
- [安全边界](#安全边界)
- [故障排查](#故障排查)
- [开发与测试](#开发与测试)
- [发布到 GitHub](#发布到-github)
- [许可证与商标](#许可证与商标)

## 核心功能

### Codex 原生对话工作流

- 使用 `$ampero-tone` Skill 作为用户入口，不重复实现另一套聊天网页或桌面聊天界面。
- 依次收集吉他/拾音器与输出设备信息，避免在关键上下文未知时猜参数。
- 对指定歌曲、艺人、专辑或录音年代执行结构化联网调研。
- 区分来源事实、算法目录事实、音色工程推断、局限和置信度。
- 先给完整效果链与参数方案，再询问意见、目标位置和最终写入确认。
- 写入成功后可直接返回 journal 绑定的保存预览，减少一次冗余交互。

### 官方算法目录映射

- 自动寻找本机官方 Ampero II Editor 的算法 JSON 目录。
- 使用真实模型名、分类、模型码、参数名、参数 ID、范围、步进和枚举值。
- 禁止模型凭空编造算法名或协议 ID。
- 支持本地目录搜索与精确模型详情查询。

### 设备只读能力

- 枚举 Ampero II Stomp 的输入和输出端口。
- 读取当前 Scene。
- 读取完整当前预设，包括名称、Scene、槽位顺序、启用状态、模型和参数。
- 读取当前路由模板，并识别 `Parallel`、`Split->Mix`、`A/B->Y`、`Y->A/B` 和 `Serial`。
- 读取并验证 `Axx-y` 位置；例如 `A50-1` 对应线性索引 `150`。

### 受控写入能力

- 修改槽位模型和开关状态。
- 修改模型参数。
- 切换 Scene。
- 切换官方路由模板。
- 自动选择目标预设并要求设备回读目标索引。
- 每条命令写入后立即读取并验证。
- 将写前状态记录到 journal；中途失败时按相反顺序回滚已执行操作。

### 独立预设保存

- 普通 `plan apply` 只修改设备的实时编辑缓冲区，不自动保存。
- 保存只能绑定到一个状态为 `applied`、且所有命令回读成功的 journal。
- 保存前再次验证设备当前处于 journal 的精确目标位置。
- 使用目标特定口令，例如 `SAVE:A50-1`。
- `save_preview_name` 可让 tone preview 提前显示保存目标、名称、21 字节 payload 和不可回滚警告。
- Apply 成功后 CLI 自动返回已绑定 journal 的精确保存预览，用户可直接确认或拒绝保存。

### 防卡死设计

- 厂商 DLL 与 Dart bridge 在独立工作进程中运行。
- Skill wrapper 为扫描、快照、应用、回滚和保存提供外层硬超时。
- 超时后终止子进程并返回结构化 `WatchdogTimeout`，不会无限等待命令。

## 项目状态与兼容性

当前版本：**0.2.0（Alpha）**

| 项目 | 状态 |
| --- | --- |
| 操作系统 | Windows x64 |
| 已验证设备 | HOTONE Ampero II Stomp |
| Python | 3.9+，必须为 x64 |
| 官方编辑器 | 必须在本机安装；直连设备时必须关闭 |
| 算法目录 | 从本机编辑器动态读取；测试目录版本为 `v1.0.8` |
| 只读快照 | 已在真实设备验证 |
| 路由读取/Serial 切换 | 已在真实设备验证 |
| 模型与参数写入 | 已在真实设备验证 |
| 单条即时回读 | 已在真实设备验证 |
| 自动目标选择 | 已实现并验证 |
| Journal 与回滚数据 | 已实现并验证 |
| 预设保存 | 已实现；部分固件可能在实际保存后丢失正式回执 |
| Ampero II / Ampero II Stage | 尚未验证，不应假设协议完全相同 |

2026 年 7 月 18 日的真实设备测试中，一个 21 条命令的 `A50-1` 音色计划全部获得即时回读验证。预设保存 payload 也曾实际生效，但测试固件有时在保存后不再返回正式回执；遇到这种情况，控制层会保守地报告“未验证”，而不是错误宣称保存成功。

## 工作原理

```text
Codex conversation
       |
       v
ampero-tone Skill
上下文收集、联网调研、方案审批、目标审批和安全确认
       |
       v
Python package: ampero_control
目录解析、计划校验、安全限制、预览、journal、回滚和保存准备
       |
       v
Dart NativePort bridge
厂商 DLL 连接、timer pump、请求/响应和消息发送
       |
       v
HOTONE Ampero II Stomp
```

为什么需要 Dart bridge：官方 Flutter 编辑器使用 Dart DL API 和真实的 `ReceivePort.nativePort` 接收连接后的消息。普通 Python `ctypes` 可以安全完成 DLL 加载和端口扫描，但不能稳定替代这个回调模型，因此所有已连接请求都通过受监督的 Dart 子进程执行。

详细说明：

- [架构](docs/architecture.md)
- [协议兼容性说明](docs/protocol.md)
- [安全模型](docs/safety.md)
- [开发说明](docs/development.md)
- [变更记录](CHANGELOG.md)

## 环境要求

### 必需

1. **Windows x64**。
2. **HOTONE Ampero II Stomp**，通过 USB 连接。
3. **官方 Ampero II Editor**。请从 [HOTONE 官方支持页面](https://www.hotoneaudio.com/support) 安装；本项目运行时从它的安装目录读取通信 DLL 和算法目录。
4. **Python 3.9+ x64**。可从 [Python Windows 下载页面](https://www.python.org/downloads/windows/) 安装。
5. **Dart SDK 3.3+**，用于第一次构建本地 bridge。可参考 [Dart 官方安装说明](https://dart.dev/get-dart)。
6. **Codex CLI**，用于对话式 Agent 工作流。官方说明见 [OpenAI Codex CLI](https://developers.openai.com/codex/cli)。

### Codex CLI 安装

如果已经安装 Node.js/npm，可使用官方包：

```powershell
npm install -g @openai/codex
codex
```

Codex 的登录和认证方式以 OpenAI 官方文档为准。

## 安装

### 1. 克隆仓库

将下面的 `YOUR_USERNAME` 替换为实际 GitHub 用户名：

```powershell
git clone https://github.com/YOUR_USERNAME/codex4ampero.git
cd codex4ampero
```

### 2. 创建 Python 虚拟环境

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

安装后提供两个等价命令：

- `codex4ampero`：推荐的新命令名。
- `ampero-control`：为早期版本保留的兼容别名。

### 3. 配置官方编辑器位置

程序会尝试以下位置：

- 环境变量 `AMPERO_EDITOR_DIR`。
- `D:\Ampero II`。
- `%ProgramFiles%\Ampero II`。
- `%LOCALAPPDATA%\Ampero II`。
- Windows 卸载注册表中的安装目录。

如果未自动发现：

```powershell
$env:AMPERO_EDITOR_DIR = "C:\Path\To\Ampero II"
```

也可以在单次命令中传递：

```powershell
codex4ampero --editor-dir "C:\Path\To\Ampero II" --json doctor --scan
```

### 4. 构建 Dart bridge

如果 `dart.exe` 已加入 `PATH`：

```powershell
.\scripts\build-bridge.ps1
```

或者显式指定 Dart：

```powershell
.\scripts\build-bridge.ps1 -DartExe "C:\Path\To\dart.exe"
```

输出文件为 `.tools\ampero_bridge.exe`。`.tools/` 已被 Git 忽略，不会发布到仓库。

### 5. 运行诊断

确保设备已通过 USB 连接，并关闭官方 `Ampero II.exe`：

```powershell
codex4ampero --json doctor --scan
```

正常结果应包含：

- 官方编辑器安装目录。
- `HTUSBTools.dll` 加载成功。
- compiled bridge 可用。
- `Ampero II Stomp` 输入/输出端口索引。

### 6. 安装 Codex Skill

```powershell
.\scripts\install-skill.ps1 -Force
```

脚本会：

1. 将 `skills/ampero-tone` 复制到 `$CODEX_HOME\skills\ampero-tone`，默认 `$CODEX_HOME` 为 `%USERPROFILE%\.codex`。
2. 设置用户环境变量 `CODEX4AMPERO_ROOT` 为当前仓库目录。
3. 提示重启 Codex。

安装后请重新启动 Codex CLI，使新的 Skill 和环境变量生效。

## 使用 Codex Skill

推荐直接在 Codex 对话中使用：

```text
使用 $ampero-tone。先执行 doctor 和只读 device snapshot，不要修改任何参数。
```

```text
使用 $ampero-tone。我的琴是 Fender Telecaster，输出到 FRFR。
联网调研 Yorushika《花に亡霊》的过载 Solo 音色，先给详细方案和参数，不要直接写入。
```

```text
把刚才确认的方案写入 A50-1，允许自动选择目标，但先展示最终预览。
```

```text
刚才的音色太亮了，只做小幅参数调整，不换模型。
```

Skill 的标准流程：

1. 收集缺失的吉他和输出信息。
2. 运行 doctor，并读取当前设备快照。
3. 对命名歌曲/艺人执行联网调研。
4. 查询本机官方算法目录。
5. 给出完整链路、参数、理由、预期结果和局限。
6. 用户认可音色方向。
7. 确认精确 `Axx-y` 目标和自动选择行为。
8. 生成、验证并展示目标绑定计划。
9. 用户最终确认后执行 `APPLY`。
10. 写入成功后直接展示 journal 绑定保存预览。
11. 用户使用 `SAVE:Axx-y` 保存，或明确拒绝保存。
12. 根据试听反馈进行小步迭代，必要时使用 journal 回滚。

## 命令行使用

日常硬件操作推荐使用 Skill wrapper，因为它提供外层 watchdog：

```powershell
$python = ".\.venv\Scripts\python.exe"
```

### Doctor 与扫描

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json doctor --scan
```

### 当前预设快照

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json device snapshot
& $python .\skills\ampero-tone\scripts\ampero.py --json device snapshot --include-parameters
```

### 仅读取路由

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json device routing --timeout 5
```

### 查询官方算法目录

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json catalog search "blues" --category DRV
& $python .\skills\ampero-tone\scripts\ampero.py --json catalog show "Dr. Blues" --category DRV
```

### 验证与预览计划

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan validate .\examples\clear-rhythm.plan.json

& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan preview .\examples\clear-rhythm.plan.json
```

### 应用计划

没有执行参数时，`plan apply` 仍然只是预览：

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan apply .\examples\clear-rhythm.plan.json
```

实际写入必须同时提供：

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan apply .\examples\clear-rhythm.plan.json `
    --execute --confirm APPLY
```

### 回滚

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan rollback .\.ampero_journals\APPLY.journal.json

& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan rollback .\.ampero_journals\APPLY.journal.json `
    --execute --confirm ROLLBACK
```

### 保存预设

先生成不可回滚预览：

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan save .\.ampero_journals\APPLY.journal.json `
    --name "My Preset"
```

精确确认后执行：

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan save .\.ampero_journals\APPLY.journal.json `
    --name "My Preset" `
    --execute --confirm SAVE:A50-1
```

## 音色计划与保存流程

计划使用 UTF-8 JSON，当前 schema 为 `1`。示例：

```json
{
  "schema_version": 1,
  "title": "Medium overdrive lead",
  "reason": "Add sustain and midrange while preserving pick dynamics.",
  "target_patch": "A50-1",
  "select_target_patch": true,
  "save_preview_name": "Lead Tone",
  "actions": [
    {
      "type": "set_model",
      "slot": 1,
      "effect": {"name": "Dr. Blues", "category": "DRV"},
      "enabled": true
    },
    {
      "type": "set_parameter",
      "slot": 1,
      "effect": {"name": "Dr. Blues", "category": "DRV"},
      "parameter": "Gain",
      "value": 58
    }
  ]
}
```

详细 schema 见 [plan-schema.md](skills/ampero-tone/references/plan-schema.md)。

`save_preview_name` 只负责准备保存预览：

- Tone preview 中的保存预览尚未绑定 journal。
- `plan apply` 永远不会自动保存。
- Apply 成功后，CLI 使用真实成功 journal 返回已绑定预览。
- 最终保存仍需要目标特定的 `SAVE:Axx-y`。

## 安全边界

- 直连操作前必须关闭官方编辑器，避免两个进程竞争设备。
- 建议先降低耳机、音箱或 FRFR 的物理音量。
- 默认只预览；写入需要 `--execute --confirm APPLY`。
- 回滚需要 `--execute --confirm ROLLBACK`。
- 保存需要精确 `SAVE:Axx-y`，且不可由控制层回滚。
- 输出敏感参数（名称包含 level、output、master、volume）不得超过目录范围的 75%。
- 模型更换必须成功读取旧模型，才能建立可靠回滚记录。
- 每条命令都限制在安全白名单中。
- 不暴露固件、bootloader、删除预设、恢复出厂、全局 I/O 或任意 raw message。
- `--allow-unverified-reads` 仅用于受控协议研究；Skill 不会自动使用。
- 不应在演出、录音或高音量监听期间首次测试写入功能。

完整安全模型见 [docs/safety.md](docs/safety.md)。

## 故障排查

### `Official editor is running` / 端口被占用

完全退出 `Ampero II.exe`，包括后台残留进程，然后重试。官方编辑器和本项目不能同时持有直连通信状态。

### 找不到官方编辑器

```powershell
$env:AMPERO_EDITOR_DIR = "C:\Path\To\Ampero II"
codex4ampero --json doctor --scan
```

检查安装目录中是否存在：

- `Ampero II.exe`
- `assets\HTUSBTools.dll`
- `data\flutter_assets\assets\data`

### `bridge_available: false`

重新构建：

```powershell
.\scripts\build-bridge.ps1
```

确认 `.tools\ampero_bridge.exe` 已生成。

### 找不到 `codex4ampero` 仓库

重新安装 Skill：

```powershell
.\scripts\install-skill.ps1 -Force
```

或手动设置：

```powershell
$env:CODEX4AMPERO_ROOT = "C:\Path\To\codex4ampero"
```

旧环境变量 `VIBE_AMPERO_ROOT` 仍被兼容读取，但新安装只设置 `CODEX4AMPERO_ROOT`。

### `DeviceTimeoutError` 或 `WatchdogTimeout`

- 不要无限重试。
- 确认编辑器已关闭。
- 检查 USB 线和设备端口。
- 结束残留 `ampero_bridge.exe` 后仅重试一次。
- 重新插拔 USB 后先执行只读 handshake 或 snapshot。
- 如果不可回滚操作已经进入发送阶段，不要自动重复发送。

### 保存命令超时

部分固件可能已经保存，但没有返回正式响应。控制层会记录：

- 精确目标预检是否通过。
- 是否已经进入 `sending_save`。
- 是否收到正式保存响应。

当状态不明确时，不要自动重发；保留 `*.save.journal.json`，并在设备上确认或手动保存。

### 设备返回 `0xffff`

这表示协议无法确认当前补丁位置。写入默认被阻止。只有计划包含精确 `target_patch`，且用户重新确认设备屏幕上的同一 `Axx-y` 标签时，才能使用 `--confirm-device-patch` 继续。

## 开发与测试

### 仓库结构

```text
codex4ampero/
├── bridge/                      Dart FFI / NativePort bridge
├── docs/                        架构、协议、安全和开发文档
├── examples/                    Schema v1 音色计划
├── scripts/                     构建、测试和 Skill 安装脚本
├── skills/ampero-tone/          Codex Skill
├── src/ampero_control/          Python 控制层
├── tests/                       单元测试
├── pyproject.toml               Python 包元数据
└── README.md                    中英文项目说明
```

### 运行测试

```powershell
.\scripts\test.ps1
```

或者：

```powershell
$env:PYTHONPATH = "src;tests"
python -m unittest discover -s tests -v
```

### Skill 校验

如果本机 Codex 安装包含 `skill-creator`：

```powershell
python "$HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
    .\skills\ampero-tone
```

### 发布前检查

```powershell
git diff --check
.\scripts\test.ps1
.\scripts\install-skill.ps1 -Force
```

不要提交：

- `.ampero_journals/`
- `.tools/`
- 官方编辑器文件和 `HTUSBTools.dll`
- 官方算法目录
- Dart SDK
- USB 抓包、用户预设备份或包含个人路径的日志

## 发布到 GitHub

创建名为 `codex4ampero` 的空 GitHub 仓库后：

```powershell
git remote add origin https://github.com/YOUR_USERNAME/codex4ampero.git
git push -u origin main
```

如果已经存在 `origin`：

```powershell
git remote set-url origin https://github.com/YOUR_USERNAME/codex4ampero.git
git push -u origin main
```

仓库内的 `.github/workflows/tests.yml` 会在 Windows 上使用 Python 3.9 和 3.12 运行完整单元测试。

## 许可证与商标

当前仓库**尚未选择开源许可证**。在添加 `LICENSE` 前，默认版权规则适用，其他人没有自动获得复制、修改或再分发代码的许可。正式公开发布前，请根据你的目标选择 MIT、Apache-2.0、GPL 或其他许可证。

HOTONE、Ampero、Ampero II Stomp 及相关产品名称属于其各自权利人。本项目仅为识别兼容设备而使用这些名称。OpenAI、Codex 及相关名称属于 OpenAI。本项目与 HOTONE 或 OpenAI 均无隶属或官方背书关系。

---

## English

`codex4ampero` is a Codex-native tone agent and safety-focused local control layer for the **HOTONE Ampero II Stomp**.

You can ask Codex to research a song tone, inspect the current preset, propose a complete signal chain, preview exact parameter changes, apply an approved plan, prepare an irreversible save preview, refine the result from listening feedback, or roll back a failed/unwanted change.

> [!IMPORTANT]
> This is an independent compatibility-research project. It is not an official HOTONE or OpenAI product. The repository does not distribute the HOTONE editor, `HTUSBTools.dll`, firmware, the official algorithm catalog, or prebuilt vendor components.

## Features

- Codex Skill conversation flow with guitar/output context collection.
- Structured web research for artist-, song-, album-, and era-specific tones.
- Explicit separation of sourced facts, catalog facts, engineering inferences, limitations, and confidence.
- Runtime discovery of the official editor, communication DLL, and newest locally installed algorithm catalog.
- Exact catalog-backed effect, model, parameter, range, and enum resolution.
- Bounded read-only scene, preset, slot, parameter, patch-location, and routing snapshots.
- Exact `Axx-y` patch addressing and optional automatic target selection.
- Verified model, parameter, scene, and routing writes.
- Immediate per-command readback verification.
- Preflight journals and reverse-order rollback.
- Separate journal-bound preset saving with exact `SAVE:Axx-y` confirmation.
- `save_preview_name` support so apply results can immediately include the exact save preview without a redundant “Do you want to save?” round trip.
- Worker-process isolation and hard watchdog timeouts around vendor DLL operations.

## Compatibility

Current release: **0.2.0 (Alpha)**

| Item | Status |
| --- | --- |
| Operating system | Windows x64 |
| Verified hardware | HOTONE Ampero II Stomp |
| Python | 3.9+ x64 |
| Official editor | Required locally; must be closed during direct device access |
| Tested local catalog | `v1.0.8` |
| Read-only snapshots | Verified on hardware |
| Serial routing | Verified on hardware |
| Model/parameter writes | Verified on hardware |
| Immediate readbacks | Verified on hardware |
| Exact target selection | Implemented and verified |
| Journal/rollback data | Implemented and verified |
| Preset save | Implemented; some firmware may drop the official response after persisting |
| Ampero II / Ampero II Stage | Not verified; do not assume protocol equivalence |

On July 18, 2026, a real `A50-1` plan containing 21 routing/model/parameter commands completed with 21 verified readbacks. The preset-save payload has also been observed to persist on hardware, but the tested firmware can stop responding after save. In that ambiguous case the controller intentionally reports the save as unverified instead of claiming success.

## Architecture

```text
Codex conversation
       |
       v
ampero-tone Skill
research, proposal approval, destination approval, write/save gates
       |
       v
Python package: ampero_control
catalog, validation, safety, previews, journals, rollback, save preparation
       |
       v
Dart NativePort bridge
vendor DLL connection, timer pump, request/response transport
       |
       v
HOTONE Ampero II Stomp
```

Connected callbacks from the official Flutter editor rely on the Dart DL API and a real `ReceivePort.nativePort`. Python `ctypes` is used only for safe DLL diagnostics and port scanning; connected requests are delegated to a supervised Dart child process.

See [Architecture](docs/architecture.md), [Protocol notes](docs/protocol.md), [Safety](docs/safety.md), [Development](docs/development.md), and the [Changelog](CHANGELOG.md).

## Requirements

1. Windows x64.
2. HOTONE Ampero II Stomp connected over USB.
3. The official Ampero II Editor from the [HOTONE support site](https://www.hotoneaudio.com/support).
4. Python 3.9+ x64 from the [official Python downloads](https://www.python.org/downloads/windows/).
5. Dart SDK 3.3+ to build the local bridge; see [Get Dart](https://dart.dev/get-dart).
6. Codex CLI for the conversational workflow; see the [official OpenAI Codex CLI documentation](https://developers.openai.com/codex/cli).

Install Codex CLI with the official npm package when Node.js/npm is available:

```powershell
npm install -g @openai/codex
codex
```

## Installation

### 1. Clone

Replace `YOUR_USERNAME` with the actual repository owner:

```powershell
git clone https://github.com/YOUR_USERNAME/codex4ampero.git
cd codex4ampero
```

### 2. Install the Python package

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

The package installs two equivalent entry points:

- `codex4ampero` — recommended.
- `ampero-control` — backward-compatible alias.

### 3. Locate the official editor

The application checks `AMPERO_EDITOR_DIR`, common installation directories, and Windows uninstall registry entries. Override discovery when necessary:

```powershell
$env:AMPERO_EDITOR_DIR = "C:\Path\To\Ampero II"
```

### 4. Build the Dart bridge

When `dart.exe` is on `PATH`:

```powershell
.\scripts\build-bridge.ps1
```

Or specify the SDK explicitly:

```powershell
.\scripts\build-bridge.ps1 -DartExe "C:\Path\To\dart.exe"
```

The generated executable is `.tools\ampero_bridge.exe`; it is intentionally ignored by Git.

### 5. Run diagnostics

Connect the device over USB and fully close `Ampero II.exe`:

```powershell
codex4ampero --json doctor --scan
```

### 6. Install the Codex Skill

```powershell
.\scripts\install-skill.ps1 -Force
```

The installer copies the Skill to `$CODEX_HOME\skills\ampero-tone`, sets the user environment variable `CODEX4AMPERO_ROOT`, and asks you to restart Codex.

## Codex Usage

Examples:

```text
Use $ampero-tone. Run doctor and a read-only device snapshot. Do not change anything.
```

```text
Use $ampero-tone. I use a Telecaster into FRFR. Research the overdriven solo tone from a named song, then show the full chain and parameters before writing anything.
```

```text
Apply the approved plan to A50-1, allow automatic target selection, but show the exact target-bound preview first.
```

The Skill workflow deliberately separates tone approval, destination approval, final write approval, and irreversible save confirmation.

## CLI Quick Reference

Use the wrapper for hardware commands because it adds a hard watchdog:

```powershell
$python = ".\.venv\Scripts\python.exe"

& $python .\skills\ampero-tone\scripts\ampero.py --json doctor --scan
& $python .\skills\ampero-tone\scripts\ampero.py --json device snapshot --include-parameters
& $python .\skills\ampero-tone\scripts\ampero.py --json device routing --timeout 5
& $python .\skills\ampero-tone\scripts\ampero.py --json catalog search "blues" --category DRV
& $python .\skills\ampero-tone\scripts\ampero.py --json plan preview .\examples\clear-rhythm.plan.json
```

Apply an approved plan:

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan apply .\examples\clear-rhythm.plan.json `
    --execute --confirm APPLY
```

Roll back from an apply journal:

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan rollback .\.ampero_journals\APPLY.journal.json `
    --execute --confirm ROLLBACK
```

Save the verified live buffer:

```powershell
& $python .\skills\ampero-tone\scripts\ampero.py --json `
    plan save .\.ampero_journals\APPLY.journal.json `
    --name "My Preset" `
    --execute --confirm SAVE:A50-1
```

## Plan and Save Semantics

Plans are UTF-8 JSON using schema version `1`. See [the full schema](skills/ampero-tone/references/plan-schema.md).

`save_preview_name` does not save anything. It lets the tone preview show the future target/name/payload/token, and lets a successful apply response immediately return an exact journal-bound save preview. The final save remains a separate irreversible operation requiring `SAVE:Axx-y`.

## Safety Boundary

- Close the official editor before direct access.
- Start with low physical monitor/headphone/FRFR volume.
- Preview is the default.
- Writes require `--execute --confirm APPLY`.
- Rollback requires `--execute --confirm ROLLBACK`.
- Save requires exact `SAVE:Axx-y` and cannot be rolled back by this project.
- Output-sensitive parameters are capped at 75% of their declared range.
- Model changes require verified preflight reads.
- Commands are restricted to a small whitelist.
- Firmware, bootloader, delete, factory-reset, global I/O, and arbitrary raw messages are not exposed.
- Never retry an ambiguous irreversible operation indefinitely.

See [docs/safety.md](docs/safety.md).

## Troubleshooting

- **Editor/device busy:** fully close `Ampero II.exe` and any orphan `ampero_bridge.exe` process.
- **Editor not found:** set `AMPERO_EDITOR_DIR`.
- **Bridge unavailable:** run `scripts/build-bridge.ps1` and verify `.tools/ampero_bridge.exe`.
- **Repository not found by the installed Skill:** reinstall the Skill or set `CODEX4AMPERO_ROOT`.
- **Timeout:** stop after the bounded failure, check USB/editor state, and retry at most once when the operation is reversible/read-only.
- **Save timeout:** the device may have persisted while dropping the response. Preserve the save journal and do not automatically resend.
- **Patch index `0xffff`:** writes remain blocked until an exact physical display label is freshly confirmed.

## Development

Run all tests:

```powershell
.\scripts\test.ps1
```

Or directly:

```powershell
$env:PYTHONPATH = "src;tests"
python -m unittest discover -s tests -v
```

Validate the Skill when the system `skill-creator` is available:

```powershell
python "$HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
    .\skills\ampero-tone
```

Do not commit generated journals, `.tools/`, vendor binaries, official catalog data, user preset backups, or logs containing personal paths.

Windows GitHub Actions runs the unit suite on Python 3.9 and 3.12.

## Publishing to GitHub

Create an empty repository named `codex4ampero`, then run:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/codex4ampero.git
git push -u origin main
```

If `origin` already exists, use `git remote set-url origin ...` before pushing.

## License and Trademarks

**No open-source license has been selected yet.** Until a `LICENSE` file is added, default copyright law applies and others do not automatically receive permission to copy, modify, or redistribute the code. Choose an appropriate license before inviting redistribution or external contributions.

HOTONE, Ampero, Ampero II Stomp, and related product names belong to their respective owners. OpenAI and Codex belong to OpenAI. Their names are used only to identify compatibility and integration targets. This project is not affiliated with or endorsed by HOTONE or OpenAI.
