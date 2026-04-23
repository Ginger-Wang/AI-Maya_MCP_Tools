'''from typing import Dict, Any

TOOL_NAME = "launch_maya_2025"
TOOL_FUNC = "launch_maya_2025"
TOOL_DESCRIPTION = "Launch Maya 2025 GUI from the server side. This tool runs on the host, not inside Maya."
TOOL_EXECUTION = "server"

MAYA_2025_EXE = r"C:\Program Files\Autodesk\Maya2025\bin\maya.exe"


def launch_maya_2025() -> Dict[str, Any]:
    """
    通过 Windows shell 启动 Maya GUI
    （确保在当前用户桌面 Session 中显示）
    """
    import os
    import subprocess

    if not os.path.exists(MAYA_2025_EXE):
        return {"success": False,"error": f"Maya executable not found: {MAYA_2025_EXE}" }

    # 关键：使用 cmd + start，让 explorer/session 启动 GUI
    # 使用 Popen，不阻塞 MCP
    subprocess.Popen([MAYA_2025_EXE],shell=False,cwd=os.path.dirname(MAYA_2025_EXE))

    return {"success": True,"message": "Maya 2025 launch requested.","launched": True,
        "exe": MAYA_2025_EXE,}

if __name__ == "__main__":
    launch_maya_2025()

'''
from typing import Dict, Any

TOOL_NAME = "launch_maya_2025"
TOOL_FUNC = "launch_maya_2025"
TOOL_DESCRIPTION = "Launch Maya 2025 GUI from the server side. This tool runs on the host, not inside Maya."
TOOL_EXECUTION = "server"

MAYA_2025_EXE = r"C:\Program Files\Autodesk\Maya2025\bin\maya.exe"


def launch_maya_2025(wait: bool = False, timeout: float = 20.0) -> Dict[str, Any]:
    """
    Launch Maya 2025 GUI on the local machine.

    Args:
        wait (bool): If True, wait until maya.exe appears in process list.
        timeout (float): Max seconds to wait when wait=True.

    Returns:
        Dict[str, Any]: Launch result
    """
    import os
    import time
    import subprocess

    if not os.path.exists(MAYA_2025_EXE):
        raise RuntimeError(f"Maya executable not found: {MAYA_2025_EXE}")

    def _is_maya_running() -> bool:
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq maya.exe"],
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            return "maya.exe" in output.lower()
        except Exception:
            return False

    # 如果已经开着，就不重复启动
    if _is_maya_running():
        return {
            "success": True,
            "message": "Maya is already running.",
            "launched": False,
            "exe": MAYA_2025_EXE,
        }

    # cwd 必须设成 bin 目录，这样 Maya GUI 才能稳定拉起
    subprocess.Popen(
        [MAYA_2025_EXE],
        shell=False,
        cwd=os.path.dirname(MAYA_2025_EXE),
    )

    if wait:
        start = time.time()
        while time.time() - start < timeout:
            if _is_maya_running():
                return {
                    "success": True,
                    "message": "Maya 2025 launched.",
                    "launched": True,
                    "exe": MAYA_2025_EXE,
                }
            time.sleep(0.5)

        raise RuntimeError("Maya launch requested, but timed out waiting for maya.exe")

    return {
        "success": True,
        "message": "Maya 2025 launch requested.",
        "launched": True,
        "exe": MAYA_2025_EXE,
    }
