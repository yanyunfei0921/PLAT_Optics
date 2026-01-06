"""
串口通信服务模块
提供串口连接、断开、数据收发等核心功能
"""
import serial
import threading
import time
from typing import Dict, List


class SerialService:
    """串口通信服务类"""
    
    def __init__(self):
        """初始化串口服务"""
        # 存储所有连接的串口对象，格式: {device_key: serial_port}
        self._serial_connections: Dict[str, serial.Serial] = {}
        # 存储接收到的数据，格式: {device_key: [数据列表]}
        self._received_data: Dict[str, List[str]] = {}
        # 线程锁，保证线程安全
        self._lock = threading.Lock()
    
    def connect(self, device_key: str, port: str, baudrate: int, 
                data_bits: int = 8, stop_bits: float = 1, 
                parity: str = 'None', timeout: int = 1000) -> tuple:
        """
        连接串口
        
        Args:
            device_key: 设备唯一标识
            port: 串口号，如 'COM3'
            baudrate: 波特率，如 9600, 115200
            data_bits: 数据位，可选 7 或 8
            stop_bits: 停止位，可选 1, 1.5 或 2
            parity: 校验位，可选 'None', 'Even', 'Odd', 'Mark', 'Space'
            timeout: 超时时间（毫秒）
            
        Returns:
            tuple: (success: bool, message: str)
        """
        with self._lock:
            # 如果已经连接，先断开
            if device_key in self._serial_connections:
                try:
                    self._serial_connections[device_key].close()
                except serial.SerialException as e:
                    print(f"Warning: Failed to close existing connection for {device_key}: {e}")
                except Exception as e:
                    print(f"Warning: Unexpected error closing connection for {device_key}: {e}")
                del self._serial_connections[device_key]
            
            # 如果已存在接收数据缓存，清空
            if device_key in self._received_data:
                self._received_data[device_key].clear()
        
        try:
            # 转换parity参数为serial库需要的格式
            parity_map = {
                'None': serial.PARITY_NONE,
                'Even': serial.PARITY_EVEN,
                'Odd': serial.PARITY_ODD,
                'Mark': serial.PARITY_MARK,
                'Space': serial.PARITY_SPACE
            }
            parity_value = parity_map.get(parity, serial.PARITY_NONE)
            
            # 打开串口连接
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=data_bits,
                parity=parity_value,
                stopbits=stop_bits,
                timeout=timeout / 1000.0  # 转换为秒
            )
            
            with self._lock:
                self._serial_connections[device_key] = ser
                self._received_data[device_key] = []
            
            return True, f"串口 {port} 连接成功"
            
        except serial.SerialException as e:
            return False, f"{str(e)}"
        except Exception as e:
            return False, f"{str(e)}"
    
    def disconnect(self, device_key: str) -> tuple:
        """
        断开指定设备的串口连接
        
        Args:
            device_key: 设备唯一标识
            
        Returns:
            tuple: (success: bool, message: str)
        """
        with self._lock:
            if device_key not in self._serial_connections:
                return False, f"设备 {device_key} 未连接"
            
            try:
                ser = self._serial_connections[device_key]
                ser.close()
                del self._serial_connections[device_key]
                
                # 清空接收数据缓存
                if device_key in self._received_data:
                    del self._received_data[device_key]
                
                return True, "断开连接成功"
                
            except Exception as e:
                return False, f"断开连接失败: {str(e)}"
    
    def send_command(self, device_key: str, command: bytes, 
                    wait_response: bool = True,
                    response_timeout: float = 2.0) -> tuple:
        """
        向指定设备发送指令并接收返回值（二进制数据）
        
        Args:
            device_key: 设备唯一标识
            command: 要发送的指令（字节串）
            wait_response: 是否等待响应
            response_timeout: 响应超时时间（秒）
            
        Returns:
            tuple: (success: bool, message: str, response: bytes)
                    其中 response 为字节串，如果未等待响应则为 b''
        """
        with self._lock:
            if device_key not in self._serial_connections:
                return False, "设备未连接", b''
            
            ser = self._serial_connections[device_key]
            
            try:
                # 清空输入缓冲区
                ser.reset_input_buffer()
                
                # 发送字节串指令
                ser.write(command)
                
                if not wait_response:
                    return True, "指令发送成功", b''
                
                # 等待接收数据（返回字节串）
                response = self._read_response(ser, response_timeout)
                
                return True, "指令发送成功", response
                
            except Exception as e:
                return False, f"发送指令失败: {str(e)}", b''
    
    def _read_response(self, ser: serial.Serial, timeout: float) -> bytes:
        """
        从串口读取响应数据（二进制）
        
        Args:
            ser: 串口对象
            timeout: 超时时间（秒）
            
        Returns:
            bytes: 接收到的数据字节串
        """
        start_time = time.time()
        response_parts = []
        
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                # 读取可用数据
                data = ser.read(ser.in_waiting)
                response_parts.append(data)
                
                # 短暂延迟，等待更多数据到来
                time.sleep(0.01)
            else:
                # 如果没有数据，稍作等待
                time.sleep(0.01)
        
        if response_parts:
            # 合并所有接收到的数据并返回字节串
            return b''.join(response_parts)
        
        return b''
    
    def is_connected(self, device_key: str) -> bool:
        """
        检查设备是否已连接
        
        Args:
            device_key: 设备唯一标识
            
        Returns:
            bool: 是否已连接
        """
        with self._lock:
            if device_key not in self._serial_connections:
                return False
            
            ser = self._serial_connections[device_key]
            return ser.is_open
    
    def get_all_connections(self) -> List[str]:
        """
        获取所有已连接设备的key列表
        
        Returns:
            List[str]: 已连接设备的key列表
        """
        with self._lock:
            return list(self._serial_connections.keys())
    
    def connect_all(self, devices_config: List[Dict]) -> dict:
        """
        批量连接所有设备
        
        Args:
            devices_config: 设备配置列表，每个元素包含:
                {
                    'key': str,        # 设备唯一标识
                    'port': str,       # 串口号
                    'baudrate': int,   # 波特率
                    'dataBits': int,   # 数据位
                    'stopBits': float, # 停止位
                    'parity': str,     # 校验位
                    'timeout': int     # 超时时间（毫秒）
                }
        
        Returns:
            dict: {device_key: {'success': bool, 'message': str}}
        """
        result = {}
        
        for device_config in devices_config:
            device_key = device_config.get('key')
            port = device_config.get('port')
            baudrate = device_config.get('baudrate', 9600)
            data_bits = device_config.get('dataBits', 8)
            stop_bits = device_config.get('stopBits', 1)
            parity = device_config.get('parity', 'None')
            timeout = device_config.get('timeout', 1000)
            
            success, message = self.connect(
                device_key=device_key,
                port=port,
                baudrate=baudrate,
                data_bits=data_bits,
                stop_bits=stop_bits,
                parity=parity,
                timeout=timeout
            )
            
            result[device_key] = {'success': success, 'message': message}
        
        return result
    
    def disconnect_all(self) -> dict:
        """
        断开所有连接的串口
        
        Returns:
            dict: {device_key: {'success': bool, 'message': str}}
        """
        result = {}
        device_keys = list(self._serial_connections.keys())
        
        for device_key in device_keys:
            success, message = self.disconnect(device_key)
            result[device_key] = {'success': success, 'message': message}
        
        return result

    def get_all_connection_status(self, devices_key: List[str]) -> dict:
        """
        获取所有设备的连接状态

        Args:
            devices_key (List[str]): 设备键名列表

        Returns:
            dict: 包含所有设备连接状态的字典，键为设备名，值为布尔值(True表示已连接，False表示未连接)
        """
        status = {}
        for device_key in devices_key:
            is_connected = self.is_connected(device_key)
            status[device_key] = is_connected

        return status


# 创建全局串口服务实例
serial_service = SerialService()

