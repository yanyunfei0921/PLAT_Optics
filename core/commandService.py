import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .serialService import serial_service


class CommandService:
    def __init__(
        self,
        config_path: Optional[Path] = None,
        *,
        serial = serial_service,
    ) -> None:
        self._config_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._config_path: Path = (
            config_path
            if config_path is not None
            else Path(__file__).resolve().parent.parent / "static" / "configs" / "commandConfig.json"
        )
        self._serial = serial

    def clear_cache(self) -> None:
        self._config_cache = None

    def _load_config(self) -> Dict[str, Dict[str, str]]:
        if self._config_cache is not None:
            return self._config_cache
        with open(self._config_path, "r", encoding="utf-8") as f:
            self._config_cache = json.load(f)
        return self._config_cache

    def list_commands(self) -> Dict[str, list]:
        cfg = self._load_config()
        result: Dict[str, list] = {}
        for device, commands in cfg.items():
            if isinstance(commands, dict):
                result[device] = list(commands.keys())
        return result

    def send(self, device: str, cmd: str, params: Optional[Dict[str, Any]] = None, *, wait_response: bool = True, timeout: float = 2.0, encoding: str = "utf-8") -> Tuple[bool, str, bytes]:
        """
        读取模板 → 渲染 → 编码 → 发送 → 返回 (success, message, response_bytes)
        """
        cfg = self._load_config()

        try:
            template = cfg[device][cmd]
        except Exception as e:
            return False, f"指令模板未发现: {e}", b""

        # 根据前缀决定渲染与编码策略：
        # - 以 'f' 开头：去掉前缀后使用 Python 格式化占位符渲染，然后按文本编码为字节
        # - 以 'h' 开头：去掉前缀后（可选先渲染占位符），按十六进制转为字节
        # - 无前缀：按文本模板直接编码为字节
        rendered: str = ""
        cmd_bytes: bytes

        try:
            if isinstance(template, str) and template.startswith("f"):
                body = template[1:]
                rendered = body.format(**(params or {}))
                cmd_bytes = rendered.encode(encoding, errors="strict")
            elif isinstance(template, str) and template.startswith("h"):
                body = template[1:]
                body = body.format(**(params or {}))
                cmd_bytes = bytes.fromhex(body)
            else:
                cmd_bytes = template.encode(encoding, errors="strict")
        except Exception as e:
            return False, f"指令构造失败: {e}", b""

        success, message, response_bytes = self._serial.send_command(
            device_key=device,
            command=cmd_bytes,
            wait_response=wait_response,
            response_timeout=timeout,
        )

        return bool(success), str(message), response_bytes or b""

command_service = CommandService()
