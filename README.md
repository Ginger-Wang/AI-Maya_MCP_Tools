# Maya_MCP_Tools

一个面向 **Autodesk Maya + MCP（Model Context Protocol）** 的工具工程模板，
用于让 Cherry Studio / 其它 MCP Client 通过自然语言调用 Maya 工具。

当前版本基于：

- **Python commandPort: `7001`**
- **自动扫描 `tools/` 子目录中的工具文件并注册到 MCP 工具列表**
- **支持 Maya-side / Server-side 两种执行模式**
- **支持调试输出（日志 + 发往 Maya 的脚本落盘）**

---

## 1. 工程目标

本工程的目标是把 Maya 工具组织成一个可扩展、可维护、可被 AI 调用的系统：

- `scene`：场景级工具（新建/打开/保存/删除/选择/启动 Maya）
- `objects`：对象级工具（创建/复制/重命名/分组/变换/冻结/重置）
- `rig`：骨骼 / 蒙皮 / 权重 / 程序化骨架相关工具

通过 MCP，AI 不需要直接写 Maya 脚本，而是优先调用这些结构化工具。

---

## 2. 当前目录结构

```text
Maya_MCP_Tools/
├─ server.py
├─ tools/
│  ├─ __init__.py
│  ├─ objects/
│  │  ├─ __init__.py
│  │  ├─ create_cube.py
│  │  ├─ duplicate_objects.py
│  │  ├─ freeze_transform.py
│  │  ├─ group_objects.py
│  │  ├─ list_objects.py
│  │  ├─ primitive.py
│  │  ├─ rename_objects.py
│  │  ├─ reset_transform.py
│  │  └─ set_transform.py
│  ├─ rig/
│  │  ├─ __init__.py
│  │  ├─ bind_skin.py
│  │  ├─ copy_skin_weights.py
│  │  ├─ get_skin_influences.py
│  │  ├─ list_skin_clusters.py
│  │  ├─ normalize_skin_weights.py
│  │  └─ procedural_skeleton.py
│  └─ scene/
│     ├─ __init__.py
│     ├─ delete_objects.py
│     ├─ launch_maya_2025.py
│     ├─ open_file.py
│     ├─ save_file.py
│     ├─ scene_new.py
│     └─ select_objects.py
```

> 建议：
> - 继续把所有“骨骼 / 蒙皮 / 权重 / rig 原型”相关工具放在 `tools/rig/`
> - 继续把所有“对象创建 / 编辑 / 变换”相关工具放在 `tools/objects/`
> - 继续把所有“场景与文件”相关工具放在 `tools/scene/`

---

## 3. `server.py` 的职责

`server.py` 是整个工程的 MCP 入口，主要职责：

1. 启动 MCP Server
2. 递归扫描 `tools/` 下所有工具文件
3. 读取工具元数据（`TOOL_NAME / TOOL_FUNC / TOOL_DESCRIPTION / TOOL_EXECUTION`）
4. 自动把工具注册到 MCP 工具列表
5. 对于 Maya-side 工具：
   - 读取工具源码
   - 包装成可在 Maya 内执行的脚本
   - 通过 `7001` Python commandPort 发送到 Maya
6. 对于 Server-side 工具：
   - 直接在本机 Python 进程执行

---

## 4. Maya commandPort 配置

当前工程默认使用：

- **端口：`7001`**
- **类型：`sourceType="python"`**

### 推荐 `userSetup.py` 示例

```python
import maya.cmds as cmds
import maya.utils


def _open_command_port():
    if cmds.commandPort(":7001", q=True):
        try:
            cmds.commandPort(name=":7001", close=True)
        except Exception:
            pass

    cmds.commandPort(n=":7001", sourceType="python", eo=False)
    print("7001 opened as PYTHON commandPort")


maya.utils.executeDeferred(_open_command_port)
```

> 注意：
> - **必须是 `sourceType="python"`**
> - 如果不是 Python commandPort，而是 MEL commandPort，当前工程不会按预期工作

---

## 5. 工具文件规范

每个工具文件都应遵循以下格式：

```python
TOOL_NAME = "scene_new"
TOOL_FUNC = "scene_new"
TOOL_DESCRIPTION = "Create a new Maya scene."
TOOL_EXECUTION = "maya"   # 可选: "maya" / "server"


def scene_new(...):
    import maya.cmds as cmds
    ...
```

### 字段说明

- `TOOL_NAME`
  - MCP 工具在客户端中显示的名字
- `TOOL_FUNC`
  - 工具文件中实际要执行的函数名
- `TOOL_DESCRIPTION`
  - 工具描述，用于 AI / MCP Client 识别功能
- `TOOL_EXECUTION`
  - `"maya"`：在 Maya 内部执行（默认）
  - `"server"`：在 Server 进程中执行（例如启动 Maya）

---

## 6. 两种执行模式

### 6.1 Maya-side 工具

适合：

- 创建物体
- 修改变换
- 新建场景
- 打开文件
- 蒙皮与骨骼操作

执行流程：

```text
Cherry Studio / MCP Client
    ↓
server.py
    ↓
读取工具源码
    ↓
包装成 Maya Python 脚本
    ↓
通过 7001 Python commandPort 发给 Maya
    ↓
Maya 内执行并返回结果
```

### 6.2 Server-side 工具

适合：

- 启动 Maya
- 未来可能的 AI 计划生成器 / 文件生成器
- 不依赖 Maya 环境的工具

执行流程：

```text
Cherry Studio / MCP Client
    ↓
server.py
    ↓
直接 import 对应工具模块
    ↓
在本机 Python 进程执行函数
```

---

## 7. 调试输出

当前 `server.py` 支持硬日志和 Maya 脚本落盘。

### 日志文件

```text
maya_mcp_server.log
```

### 调试脚本输出目录

```text
_debug_out/
```

其中会保存每次真正发给 Maya 的 Python 脚本，方便排查：

- Cherry Studio 显示成功但 Maya 没动作
- 工具包装是否真正调用了工具函数
- 参数是否按预期传入

---

## 8. 运行方式

### 8.1 本地启动 server

你可以让 MCP Client 直接指向：

- Python 解释器：你的虚拟环境 Python
- 脚本：`server.py`

### 8.2 推荐流程

1. 启动 Maya（并确保 7001 Python commandPort 已打开）
2. 启动 / 连接 MCP Client（例如 Cherry Studio）
3. 确认工具列表正常显示
4. 先测试最小工具：
   - `scene_new`
   - `create_cube`
   - `set_transform`

---

## 9. 已有工具概览

### 9.1 `scene`

- `scene_new`
  - 新建场景
- `open_file`
  - 打开场景文件
- `save_file`
  - 保存场景文件
- `delete_objects`
  - 删除对象
- `select_objects`
  - 选择对象
- `launch_maya_2025`
  - 启动 Maya 2025（Server-side）

### 9.2 `objects`

- `create_cube`
  - 创建 cube
- `primitive`
  - 创建基础几何体
- `duplicate_objects`
  - 复制对象
- `rename_objects`
  - 重命名对象
- `group_objects`
  - 分组对象
- `list_objects`
  - 查询对象
- `set_transform`
  - 设置平移/旋转/缩放
- `freeze_transform`
  - 冻结变换
- `reset_transform`
  - 重置变换

### 9.3 `rig`

- `bind_skin`
  - 绑定蒙皮
- `copy_skin_weights`
  - 复制权重 / 替换骨骼
- `get_skin_influences`
  - 获取 influence
- `list_skin_clusters`
  - 列出 skinCluster
- `normalize_skin_weights`
  - 权重归一化
- `procedural_skeleton`
  - 程序化骨架生成器

---

## 10. 推荐的开发原则

### 10.1 顶层不要 import maya
不要这样写：

```python
import maya.cmds as cmds
```

因为 `server.py` 会先在普通 Python 环境中扫描工具文件，
如果在文件顶层 import `maya`，会导致：

```python
No module named 'maya'
```

### 正确做法

```python
def some_tool(...):
    import maya.cmds as cmds
    ...
```

---

### 10.2 对输入做 LLM 友好兼容
建议支持：

- `"a b c"`
- `"a,b,c"`
- `['a', 'b', 'c']`

因为 MCP / Cherry Studio / AI 在传参时，可能会把列表变成字符串。

---

### 10.3 返回真实结果，不返回空 success
工具应该尽量返回：

- 真实创建出来的对象名
- 实际影响到的节点
- 查询结果
- 失败原因

而不是只返回：

```python
{"success": True}
```

---

## 11. 当前已知注意事项

### 11.1 不要把不符合工具规范的旧文件留在 `tools/` 里
例如：

- 旧版实验脚本
- 文档生成器
- 没有 `TOOL_FUNC` 对应函数的文件

否则自动扫描时会报：

```text
module 'xxx' has no attribute 'xxx'
```

---

### 11.2 如果 Cherry Studio 显示成功，但 Maya 没动作
优先检查：

1. `maya_mcp_server.log`
2. `_debug_out/` 下生成的 Maya 执行脚本
3. Maya 的 7001 是否真的是 Python commandPort
4. `server.py` 是否是当前最新版本

---

## 12. 后续建议

建议接下来按以下方向继续扩展：

### `objects/`
- `match_transform.py`
- `parent_objects.py`
- `unparent_objects.py`

### `rig/`
- `add_influence.py`
- `remove_influence.py`
- `prune_skin_weights.py`
- `bind_skeleton_to_mesh.py`
- `procedural_skeleton` 的 subtype / orient 增强

### AI / 自动化
- `ai_plan_generator.py`
- `plan_executor.py`
- 让 AI 优先生成“工具调用计划”而不是直接写 Maya 脚本

---

## 13. 推荐的 AI 使用方式

最推荐的路径不是让 AI 直接生成任意 Maya 脚本，
而是让 AI：

1. 先生成结构化计划（JSON / steps）
2. 再调用当前已有工具

例如：

```json
{
  "plan": [
    {
      "tool": "primitive",
      "args": {
        "primitive_type": "cube",
        "name": "blockA"
      }
    },
    {
      "tool": "set_transform",
      "args": {
        "node": "blockA",
        "translate": [0, 5, 0]
      }
    }
  ]
}
```

这样比“AI 直接生成裸 Maya 脚本”更稳定、更可维护、更可审计。

---

## 14. 版本建议

当前建议你把“现在能跑通的版本”做一个稳定快照，例如：

```text
E:\Maya_MCP_Tools_stable_20260422
```

这样后面继续加工具时，如果某次改动引入问题，可以快速回滚。

---

## 15. 最后一句

当前这套工程已经具备：

- Maya 通信
- 工具自动发现
- 多目录组织
- Maya-side / Server-side 分流
- 调试落盘能力

接下来最值得投入的方向，不再是通信层，而是：

> **持续补工具能力 + 让 AI 更好地调用这些工具**
