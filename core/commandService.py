import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from .serialService import serial_service
from .databaseService import db_service


class CommandService:
    # 需要验证返回值的设备列表
    DEVICES_REQUIRE_RESPONSE_CHECK = ["light_source", "delay_module"]

    def __init__(
        self,
        config_path: Optional[Path] = None,
        app_config_path: Optional[Path] = None,
        *,
        serial = serial_service,
    ) -> None:
        self._config_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._app_config_cache: Optional[Dict[str, Any]] = None
        self._config_path: Path = (
            config_path
            if config_path is not None
            else Path(__file__).resolve().parent.parent / "config" / "commandConfig.json"
        )
        self._app_config_path: Path = (
            app_config_path
            if app_config_path is not None
            else Path(__file__).resolve().parent.parent / "config" / "app_config.json"
        )
        self._serial = serial

    def clear_cache(self) -> None:
        self._config_cache = None
        self._app_config_cache = None

    def _load_config(self) -> Dict[str, Dict[str, str]]:
        if self._config_cache is not None:
            return self._config_cache
        with open(self._config_path, "r", encoding="utf-8") as f:
            self._config_cache = json.load(f)
        return self._config_cache

    def _load_app_config(self) -> Dict[str, Any]:
        """加载应用配置（包含串口调试模式设置）"""
        if self._app_config_cache is not None:
            return self._app_config_cache
        try:
            with open(self._app_config_path, "r", encoding="utf-8") as f:
                self._app_config_cache = json.load(f)
        except Exception:
            self._app_config_cache = {}
        return self._app_config_cache

    def is_debug_mode(self) -> bool:
        """检查是否处于调试模式（调试模式下所有指令无需等待返回值）"""
        app_cfg = self._load_app_config()
        serial_cfg = app_cfg.get("serial", {})
        return serial_cfg.get("debug_mode", False)

    def get_serial_config(self) -> Dict[str, Any]:
        """获取串口配置参数"""
        app_cfg = self._load_app_config()
        return app_cfg.get("serial", {})

    def list_commands(self) -> Dict[str, list]:
        cfg = self._load_config()
        result: Dict[str, list] = {}
        for device, commands in cfg.items():
            if isinstance(commands, dict):
                result[device] = list(commands.keys())
        return result

    def send(self, device: str, cmd: str, params: Optional[Dict[str, Any]] = None, *, wait_response: bool = True, timeout: float = 2.0, encoding: str = "utf-8") -> Tuple[bool, str, bytes, Optional[Dict]]:
        """
        读取模板 → 渲染 → 编码 → 发送 → 返回 (success, message, response_bytes, decode_result)

        注意：
            - 调试模式下（debug_mode=True），所有指令强制不等待返回值，不验证
            - 工作模式下（debug_mode=False），按 wait_response 参数决定是否等待
            - light_source 和 delay_module 设备会验证返回值
            - three_axis_motor 不验证返回值

        Returns:
            Tuple[bool, str, bytes, Optional[Dict]]:
                - success: 指令发送是否成功（工作模式下包含返回值验证结果）
                - message: 提示消息
                - response_bytes: 原始响应字节
                - decode_result: 解码结果字典（如有），包含验证详情
        """
        cfg = self._load_config()
        serial_cfg = self.get_serial_config()

        # 调试模式下强制不等待响应
        debug_mode = self.is_debug_mode()
        actual_wait_response = False if debug_mode else wait_response

        # 从配置获取超时参数
        default_timeout = serial_cfg.get("default_timeout_ms", 2000) / 1000.0
        idle_timeout = serial_cfg.get("idle_timeout_ms", 100) / 1000.0
        actual_timeout = timeout if timeout != 2.0 else default_timeout

        try:
            template = cfg[device][cmd]
        except Exception as e:
            return False, f"指令模板未发现: {e}", b"", None

        # 根据前缀决定渲染与编码策略
        cmd_bytes: bytes

        try:
            if template == "dynamic":
                encoder_name = f"_encode_{device}_{cmd}"
                encoder = getattr(self, encoder_name, None)
                if encoder is None:
                    return False, f"动态指令编码方法未找到: {encoder_name}", b"", None
                cmd_bytes = encoder(**(params or {}))
            elif isinstance(template, str) and template.startswith("f"):
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
            return False, f"指令构造失败: {e}", b"", None

        # 发送指令
        success, message, response_bytes = self._serial.send_command(
            device_key=device,
            command=cmd_bytes,
            wait_response=actual_wait_response,
            response_timeout=actual_timeout,
            idle_timeout=idle_timeout,
        )

        # 调试模式提示
        if debug_mode and wait_response:
            message = f"{message} (调试模式，未等待响应)"
            # 记录串口日志
            try:
                port = self._serial.get_port(device) if hasattr(self._serial, 'get_port') else ''
                db_service.log_serial_command(
                    device=device,
                    port=port,
                    command=cmd,
                    params=params,
                    cmd_bytes=cmd_bytes,
                    response_bytes=response_bytes,
                    success=success,
                    message=message
                )
            except Exception:
                pass
            return bool(success), str(message), response_bytes or b"", None

        # 工作模式下，对需要验证的设备进行返回值检查
        decode_result = None
        if success and actual_wait_response and device in self.DEVICES_REQUIRE_RESPONSE_CHECK:
            decode_result = self._decode_response(device, cmd, cmd_bytes, response_bytes)
            if decode_result is not None:
                if not decode_result.get("success", False):
                    success = False
                    message = decode_result.get("error", "返回值验证失败")
                else:
                    message = "指令执行成功，返回值验证通过"

        # 记录串口日志
        try:
            port = self._serial.get_port(device) if hasattr(self._serial, 'get_port') else ''
            db_service.log_serial_command(
                device=device,
                port=port,
                command=cmd,
                params=params,
                cmd_bytes=cmd_bytes,
                response_bytes=response_bytes,
                success=success,
                message=message
            )
        except Exception:
            pass  # 日志记录失败不影响主流程

        return bool(success), str(message), response_bytes or b"", decode_result

    def _decode_response(self, device: str, cmd: str, cmd_bytes: bytes, response: bytes) -> Optional[Dict]:
        """
        解析设备返回值

        Args:
            device: 设备名
            cmd: 指令名
            cmd_bytes: 发送的指令字节
            response: 返回的响应字节

        Returns:
            解码结果字典，包含 success 字段
        """
        decoder_name = f"_decode_{device}_{cmd}"
        decoder = getattr(self, decoder_name, None)
        if decoder is None:
            # 没有对应的解码方法，跳过验证
            return None
        try:
            return decoder(cmd_bytes, response)
        except Exception as e:
            return {"success": False, "error": f"返回值解析异常: {e}"}

    # ===================== 动态指令编码方法 =====================
    def _encode_delay_module_set_delay_time(self, delay_time_us: int) -> bytes:
        """
        设置延时模块延时时间

        Args:
            delay_time_us: 需要设置的延时时间，单位为微秒 (µs)，有效范围 1-200 µs

        Returns:
            编码后的5字节指令
        """
        if not (1 <= delay_time_us <= 200):
            raise ValueError("延时时间 (delay_time_us) 必须在 1 到 200 微秒之间")

        delay_time_ns = delay_time_us * 1000
        value_16bit = delay_time_ns // 20
        byte2 = (value_16bit >> 8) & 0xFF
        byte3 = value_16bit & 0xFF
        checksum = (0xAB + byte2 + byte3) % 256
        return bytes([0x5A, 0xAB, byte2, byte3, checksum])

    # ===================== 返回值解码方法 =====================
    # --------------------- light_source ---------------------
    def _decode_light_source_set_indicator_laser_power(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """解析指示激光功率设置返回值 - 回显验证"""
        if response == cmd_bytes:
            return {"success": True}
        return {"success": False, "error": f"返回值不匹配，期望: {cmd_bytes.hex()}, 实际: {response.hex()}"}

    def _decode_light_source_set_visible_light_power(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """解析可见光功率设置返回值 - 回显验证"""
        if response == cmd_bytes:
            return {"success": True}
        return {"success": False, "error": f"返回值不匹配，期望: {cmd_bytes.hex()}, 实际: {response.hex()}"}

    def _decode_light_source_set_blackbody_temperature(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """
        解析黑体温度设置返回值

        返回格式: *XXXXXXHYYYYYY# 或 *XXXXXXLYYYYYY#
        其中 XXXXXX 是设置温度，H/L 表示正/负，YYYYYY 是当前温度（单位0.001°C）
        """
        try:
            response_str = response.decode('ascii')
            if len(response_str) == 15 and response_str[0] == '*' and response_str[-1] == '#':
                sign_char = response_str[7]  # H或L
                if sign_char in ('H', 'L'):
                    temp_str = response_str[8:14]
                    real_temp = int(temp_str) / 1000.0
                    if sign_char == 'L':
                        real_temp = -real_temp
                    return {"success": True, "temperature": real_temp}
            return {"success": False, "error": f"返回值格式错误: {response_str}"}
        except Exception as e:
            return {"success": False, "error": f"解析失败: {e}, 原始数据: {response.hex()}"}

    # --------------------- delay_module ---------------------
    def _decode_delay_module_open(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """解析延时模块打开返回值"""
        expected = bytes.fromhex("aa bb cc dd 01")
        if response == expected:
            return {"success": True}
        return {"success": False, "error": f"返回值不匹配，期望: {expected.hex()}, 实际: {response.hex()}"}

    def _decode_delay_module_close(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """解析延时模块关闭返回值"""
        expected = bytes.fromhex("aa bb cc dd 00")
        if response == expected:
            return {"success": True}
        return {"success": False, "error": f"返回值不匹配，期望: {expected.hex()}, 实际: {response.hex()}"}

    def _decode_delay_module_delay_time_add_4ns(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """解析延时模块增加4ns返回值"""
        expected = bytes.fromhex("aa bb cc dd 02")
        if response == expected:
            return {"success": True}
        return {"success": False, "error": f"返回值不匹配，期望: {expected.hex()}, 实际: {response.hex()}"}

    def _decode_delay_module_set_delay_time(self, cmd_bytes: bytes, response: bytes) -> Dict:
        """解析延时模块设置延时时间返回值"""
        expected = bytes.fromhex("aa bb cc dd 03")
        if response == expected:
            return {"success": True}
        return {"success": False, "error": f"返回值不匹配，期望: {expected.hex()}, 实际: {response.hex()}"}


command_service = CommandService()
