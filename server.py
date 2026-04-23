import os
import json
import time
import socket
import inspect
import importlib.util
import logging
import traceback
from typing import Sequence, List, Any, Dict, Optional, get_origin
from itertools import chain

from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from mcp.server.fastmcp.utilities.types import Image
from mcp.server.fastmcp.server import Context
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import pydantic_core


__version__ = "0.1.0"

# ------------------------------------------------------------
# 基础路径与配置
# ------------------------------------------------------------
SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIRECTORY = os.path.join(SCRIPT_DIRECTORY, "tools")
DEBUG_DIRECTORY = os.path.join(SCRIPT_DIRECTORY, "_debug_out")

LOCAL_HOST = "127.0.0.1"
DEFAULT_COMMAND_PORT = 7001
SOCKET_RECV_SIZE = 4096
DEFAULT_SOCKET_TIMEOUT = 5.0

# 硬日志开关
DEBUG_SAVE_MAYA_SCRIPT = True       # 保存每次发给 Maya 的脚本
DEBUG_LOG_MAYA_SCRIPT = True        # 在日志里打印脚本全文
DEBUG_LOG_SOCKET = True             # 打印 socket 连接 / 发送 / 接收过程
DEBUG_LOG_TOOL_DISCOVERY = True     # 打印工具扫描过程

os.makedirs(DEBUG_DIRECTORY, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(SCRIPT_DIRECTORY, "maya_mcp_server.log"),
            encoding="utf-8"
        ),
    ],
)

logger = logging.getLogger("Maya_MCP")

_operation_manager = None


# ============================================================
# MayaConnection
# 只负责：通过 7001 Python commandPort 发送 Python 脚本
# ============================================================
class MayaConnection:
    """Python commandPort 7001 connection for Maya."""

    def __init__(
        self,
        host: str = LOCAL_HOST,
        port: int = DEFAULT_COMMAND_PORT,
        timeout: float = DEFAULT_SOCKET_TIMEOUT,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send_python_command(self, script: str) -> Optional[str]:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(self.timeout)

        if DEBUG_LOG_SOCKET:
            logger.info(f"[SOCKET_CONNECT] host={self.host} port={self.port} timeout={self.timeout}")

        client.connect((self.host, self.port))

        try:
            payload = script
            if not payload.endswith("\n"):
                payload += "\n"

            encoded = payload.encode("utf-8")

            if DEBUG_LOG_SOCKET:
                logger.info(f"[SOCKET_SEND] bytes={len(encoded)}")

            client.send(encoded)

            chunks = []
            while True:
                try:
                    data = client.recv(SOCKET_RECV_SIZE)
                except socket.timeout:
                    if DEBUG_LOG_SOCKET:
                        logger.info("[SOCKET_RECV] timeout reached")
                    break

                if not data:
                    if DEBUG_LOG_SOCKET:
                        logger.info("[SOCKET_RECV] empty chunk, stop")
                    break

                chunks.append(data)

                if DEBUG_LOG_SOCKET:
                    logger.info(f"[SOCKET_RECV] chunk_bytes={len(data)}")

                if len(data) < SOCKET_RECV_SIZE:
                    break

            if not chunks:
                if DEBUG_LOG_SOCKET:
                    logger.info("[SOCKET_RESULT] no data returned")
                return None

            result = b"".join(chunks).decode("utf-8", errors="ignore")

            if DEBUG_LOG_SOCKET:
                preview = result[:500].replace("\n", "\\n")
                logger.info(f"[SOCKET_RESULT] chars={len(result)} preview={preview}")

            return result

        finally:
            client.close()

    def run_python_script(self, python_script: str):
        result = self._send_python_command(python_script)

        if isinstance(result, str):
            result = result.rstrip("\x00\r\n")

        if isinstance(result, str):
            try:
                return json.loads(result)
            except Exception:
                return result

        return result


# ============================================================
# OperationsManager
# 自动扫描 tools/ 下所有工具
# ============================================================
class OperationsManager:
    def __init__(self):
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._tools: Dict[str, Tool] = {}

    def get_entry(self, name: str) -> Optional[Dict[str, Any]]:
        return self._entries.get(name)

    def get_tools(self) -> List:
        return list(self._tools.values())

    def find_tools(self):
        """
        递归扫描 tools/ 下所有 .py 文件，自动注册工具。

        跳过：
        - __init__.py
        - 以 _ 开头的目录 / 文件
        - 不符合 TOOL_NAME / TOOL_FUNC / 函数存在规范的文件
        """
        if not os.path.isdir(TOOLS_DIRECTORY):
            logger.warning(f"Tools directory not found: {TOOLS_DIRECTORY}")
            return

        if DEBUG_LOG_TOOL_DISCOVERY:
            logger.info(f"[DISCOVERY_ROOT] {TOOLS_DIRECTORY}")

        for root, dirs, files in os.walk(TOOLS_DIRECTORY):
            # ✅ 跳过 _core / 私有目录
            dirs[:] = [d for d in dirs if not d.startswith("_") and not d.startswith(".")]

            if DEBUG_LOG_TOOL_DISCOVERY:
                logger.info(f"[DISCOVERY_DIR] {root}")

            for file in files:
                if not file.endswith(".py"):
                    continue

                if file == "__init__.py" or file.startswith("_"):
                    if DEBUG_LOG_TOOL_DISCOVERY:
                        logger.info(f"[DISCOVERY_SKIP_FILE] {os.path.join(root, file)}")
                    continue

                path = os.path.join(root, file)

                if DEBUG_LOG_TOOL_DISCOVERY:
                    logger.info(f"[DISCOVERY_FILE] {path}")

                metadata = self._get_function_tool(path)

                if not metadata:
                    continue

                tool = metadata["tool"]
                tool_name = tool.name

                if tool_name in self._tools:
                    logger.warning(f"Duplicate tool name detected, skipping: {tool_name} ({path})")
                    continue

                self._entries[tool_name] = metadata
                self._tools[tool_name] = tool

                logger.info(
                    f"[REGISTERED] tool={tool_name} execution={metadata['execution']} path={path}"
                )

    @staticmethod
    def _get_function_tool(filename: str) -> Optional[Dict[str, Any]]:
        """
        支持工具文件中定义：
            TOOL_NAME
            TOOL_FUNC
            TOOL_DESCRIPTION
            TOOL_EXECUTION = "maya" / "server"
        """
        base_name = os.path.splitext(os.path.basename(filename))[0]

        try:
            spec = importlib.util.spec_from_file_location(base_name, filename)
            if spec is None or spec.loader is None:
                logger.error(f"Unable to create import spec for: {filename}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            tool_name = getattr(module, "TOOL_NAME", base_name)
            func_name = getattr(module, "TOOL_FUNC", base_name)
            tool_desc = getattr(module, "TOOL_DESCRIPTION", None)
            execution = getattr(module, "TOOL_EXECUTION", "maya")

            fn = getattr(module, func_name)
            if not callable(fn):
                logger.error(f"{filename}: {func_name} is not callable")
                return None

        except Exception as e:
            logger.error(f"Unable to pre-load tool from {filename} because: {e}")
            logger.debug(traceback.format_exc())
            return None

        func_doc = tool_desc or (fn.__doc__ or "")
        sig = inspect.signature(fn)

        context_kwarg = None
        for param_name, param in sig.parameters.items():
            annotation = param.annotation

            if annotation is inspect._empty:
                continue

            if get_origin(annotation) is not None:
                continue

            if isinstance(annotation, type) and issubclass(annotation, Context):
                context_kwarg = param_name
                break

        func_arg_metadata = func_metadata(
            fn,
            skip_names=[context_kwarg] if context_kwarg is not None else [],
        )
        parameters = func_arg_metadata.arg_model.model_json_schema()

        tool = Tool(
            name=tool_name,
            description=func_doc,
            inputSchema=parameters,
        )

        return {
            "tool": tool,
            "path": filename,
            "func_name": func_name,
            "execution": execution,  # "maya" / "server"
        }


# ============================================================
# Maya-side 工具包装
# 关键修复点：确保在 Maya 中真正调用 tool_func(...)
# ============================================================
def build_maya_execution_script(
    python_script: str,
    maya_function_name: str,
    arg_names: List[str],
    arg_values: Dict[str, Any],
) -> str:
    """
    把工具文件源码包装成 Maya 内可执行脚本，并真正调用工具函数。
    """
    spaced_python_script = "    " + python_script.replace("\n", "\n    ")

    # _mcp_tool_scope 的函数签名
    arg_sig = ", ".join(arg_names)
    if arg_sig:
        func_header = f"def _mcp_tool_scope({arg_sig}):"
    else:
        func_header = "def _mcp_tool_scope():"

    # 在 Maya 作用域里真正调用工具函数
    inner_call_args = ", ".join([f"{name}={name}" for name in arg_names])
    if inner_call_args:
        tool_call = f"    return {maya_function_name}({inner_call_args})"
    else:
        tool_call = f"    return {maya_function_name}()"

    # 从 server 侧把参数真实字面量传进去
    outer_call_parts = [f"{k}={repr(v)}" for k, v in arg_values.items()]
    outer_call = ", ".join(outer_call_parts)
    if outer_call:
        scope_call = f"_mcp_results = _mcp_tool_scope({outer_call})"
    else:
        scope_call = "_mcp_results = _mcp_tool_scope()"

    return f"""
import json
import traceback
from pprint import pprint

{func_header}
{spaced_python_script}
{tool_call}

try:
    {scope_call}
except Exception as e:
    traceback.print_exc()
    _mcp_results = {{
        "success": False,
        "message": "Error: Maya tool failed with the following message: " + str(e),
        "traceback": traceback.format_exc(),
    }}

if _mcp_results is None:
    print(json.dumps({{"success": True}}))
elif isinstance(_mcp_results, str):
    print(_mcp_results)
else:
    try:
        print(json.dumps(_mcp_results))
    except Exception:
        pprint(_mcp_results)
        print(str(_mcp_results))
"""


def load_maya_tool_source(
    func_name: str,
    filename: str,
    vars: Optional[Dict[str, Any]] = None,
    *,
    tool_name_for_log: str = "",
) -> str:
    vars = vars or {}

    with open(filename, "r", encoding="utf-8") as f:
        script = f.read()

    result_script = build_maya_execution_script(
        python_script=script,
        maya_function_name=func_name,
        arg_names=list(vars.keys()),
        arg_values=vars,
    )

    # --------------------------------------------
    # 硬日志：把最终发给 Maya 的脚本保存下来
    # --------------------------------------------
    if DEBUG_SAVE_MAYA_SCRIPT:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_tool_name = tool_name_for_log or func_name
        debug_file = os.path.join(
            DEBUG_DIRECTORY,
            f"{stamp}_{safe_tool_name}_maya_exec.py"
        )
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(result_script)
        logger.info(f"[MAYA_SCRIPT_FILE] {debug_file}")

    if DEBUG_LOG_MAYA_SCRIPT:
        logger.info(f"[MAYA_SCRIPT_BEGIN] tool={tool_name_for_log or func_name}")
        logger.debug(result_script)
        logger.info(f"[MAYA_SCRIPT_END] tool={tool_name_for_log or func_name}")

    return result_script


# ============================================================
# Server-side 工具执行
# 例如 launch_maya_2025
# ============================================================
def run_server_side_tool(
    filename: str,
    func_name: str,
    arguments: Dict[str, Any],
):
    base_name = os.path.splitext(os.path.basename(filename))[0]

    spec = importlib.util.spec_from_file_location(base_name, filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to create import spec for: {filename}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fn = getattr(module, func_name)
    if not callable(fn):
        raise RuntimeError(f"{func_name} is not callable in {filename}")

    arguments = arguments or {}
    return fn(**arguments)


# ============================================================
# 把 Python 结果转成 MCP content
# ============================================================
def convert_to_content(
    result: Any,
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    if result is None:
        return []

    if isinstance(result, (TextContent, ImageContent, EmbeddedResource)):
        return [result]

    if isinstance(result, Image):
        return [result.to_image_content()]

    if isinstance(result, (list, tuple)):
        return list(chain.from_iterable(convert_to_content(item) for item in result))

    if not isinstance(result, str):
        try:
            result = json.dumps(pydantic_core.to_jsonable_python(result))
        except Exception:
            result = str(result)

    return [TextContent(type="text", text=result)]


# ============================================================
# MCP Server
# ============================================================
server = Server("Maya_MCP_Tools")


@server.list_tools()
async def handle_list_tools() -> list:
    logger.info("[LIST_TOOLS] request received")
    if _operation_manager is None:
        return []
    return _operation_manager.get_tools()


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict | None,
) -> list[TextContent | ImageContent | EmbeddedResource]:
    arguments = arguments or {}

    logger.info(f"[CALL] tool={name} args={arguments}")

    if _operation_manager is None:
        return convert_to_content({
            "success": False,
            "message": "Operation manager is not initialized."
        })

    entry = _operation_manager.get_entry(name)
    if not entry:
        error_msg = f"Tool {name} not found."
        logger.error(error_msg)
        return convert_to_content({
            "success": False,
            "message": error_msg
        })

    try:
        execution = entry.get("execution", "maya")
        logger.info(f"[CALL_MODE] tool={name} execution={execution}")

        # --------------------------------------------------
        # server-side tool
        # --------------------------------------------------
        if execution == "server":
            logger.info(f"[SERVER_EXEC] tool={name}")
            results = run_server_side_tool(
                filename=entry["path"],
                func_name=entry["func_name"],
                arguments=arguments,
            )
            logger.info(f"[SERVER_EXEC_DONE] tool={name} results_type={type(results).__name__}")
            return convert_to_content(results)

        # --------------------------------------------------
        # maya-side tool（直接执行，不做 preflight）
        # --------------------------------------------------
        logger.info(f"[MAYA_EXEC] tool={name} func={entry['func_name']} file={entry['path']}")
        maya_conn = MayaConnection()

        python_script = load_maya_tool_source(
            func_name=entry["func_name"],
            filename=entry["path"],
            vars=arguments,
            tool_name_for_log=name,
        )

        results = maya_conn.run_python_script(python_script)

        logger.info(f"[MAYA_RESULT_RAW] tool={name} result_type={type(results).__name__} result={results}")

        converted_results = convert_to_content(results)

        logger.info(f"[MAYA_RESULT_CONTENT] tool={name} content_count={len(converted_results)}")

        if converted_results:
            return converted_results

        return convert_to_content({"success": True})

    except Exception as e:
        logger.critical(e, exc_info=True)
        error_msg = f"Error: tool {name} failed to run. Reason: {e}"
        logger.error(error_msg)
        return convert_to_content({
            "success": False,
            "message": error_msg
        })


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="Maya_MCP_Tools",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    _operation_manager = OperationsManager()
    _operation_manager.find_tools()

    logger.info(f"Maya_MCP_Tools v{__version__} server starting up")
    logger.info(f"Using tools directory: {TOOLS_DIRECTORY}")
    logger.info(f"Using Maya commandPort: {DEFAULT_COMMAND_PORT}")
    logger.info("Using commandPort source type: python")
    logger.info(f"Debug output directory: {DEBUG_DIRECTORY}")

    import asyncio
    asyncio.run(run())
