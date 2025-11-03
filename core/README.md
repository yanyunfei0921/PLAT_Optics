# 串口通信服务使用说明

## 概述

`serialService.py` 提供了完整的串口通信功能，支持多设备管理、数据收发等功能。

## 主要功能

### 1. 连接串口
```python
success, message = serial_service.connect(
    device_key='light_source',  # 设备唯一标识
    port='COM3',                # 串口号
    baudrate=9600,              # 波特率
    data_bits=8,                # 数据位
    stop_bits=1,                # 停止位
    parity='None',              # 校验位
    timeout=1000                # 超时（毫秒）
)
```

### 2. 发送指令并接收返回值（二进制数据）

**重要说明**：串口服务只负责二进制数据的传输，不处理编码/解码。编码解码应在命令解析模块完成。

```python
# 发送文本指令（需要先编码为字节串）
command_text = '*IDN?\n'
command_bytes = command_text.encode('utf-8')  # 文本 -> 字节串
success, message, response_bytes = serial_service.send_command(
    device_key='light_source',
    command=command_bytes,      # 传入字节串
    wait_response=True,         # 是否等待响应
    response_timeout=2.0        # 响应超时（秒）
)

# 接收到的也是字节串，需要自己解码
response_text = response_bytes.decode('utf-8')  # 字节串 -> 文本


# 发送十六进制指令
hex_str = "01 02 03 FF"
command_bytes = bytes.fromhex(hex_str.replace(' ', ''))  # 十六进制字符串 -> 字节串
success, message, response_bytes = serial_service.send_command(
    device_key='three_axis_motor',
    command=command_bytes,
    wait_response=True
)
```

### 3. 测试设备
```python
# 测试设备（发送 *IDN? 并接收响应）
test_command = '*IDN?\n'.encode('utf-8')
success, message, response_bytes = serial_service.send_command(
    device_key='light_source',
    command=test_command
)
if success:
    response_text = response_bytes.decode('utf-8')
    print(f"设备响应: {response_text}")
```

### 4. 检查连接状态
```python
is_connected = serial_service.is_connected('light_source')
```

### 5. 断开连接
```python
success, message = serial_service.disconnect('light_source')
```

### 6. 批量操作
```python
# 断开所有设备
results = serial_service.disconnect_all()

# 获取所有已连接设备
connected_devices = serial_service.get_all_connections()

# 获取可用串口号
available_ports = serial_service.get_available_ports()
```

## API 接口

前端通过以下 API 调用串口服务：

### 连接串口
```
POST /api/serial/connect
{
  "deviceKey": "light_source",
  "port": "COM3",
  "baudrate": 9600,
  "dataBits": 8,
  "stopBits": 1,
  "parity": "None",
  "timeout": 1000
}
```

### 发送指令
```
POST /api/serial/send-command
{
  "deviceKey": "light_source",
  "command": "*IDN?",              // 字符串指令
  "encoding": "utf-8",             // 可选: "utf-8" 或 "hex"
  "waitResponse": true,
  "responseTimeout": 2.0
}

// 返回的 response 是 base64 编码的字符串
// responseFormat 字段指示返回格式为 "base64"
// 前端需要 base64 解码后使用

// 十六进制指令示例
{
  "deviceKey": "three_axis_motor",
  "command": "01 02 03 FF",
  "encoding": "hex"
}
```

### 断开连接
```
POST /api/serial/disconnect
{
  "deviceKey": "light_source"
}
```

### 批量连接
```
POST /api/serial/connect-all
```

### 获取连接状态
```
GET /api/serial/status
```

### 获取可用串口
```
GET /api/serial/ports
```

## 注意事项

1. **线程安全**: 服务使用了线程锁，支持多线程环境下的并发操作
2. **编码支持**: 支持 UTF-8 文本和十六进制数据发送
3. **自动缓冲**: 发送文本指令时会自动添加换行符 `\r\n`
4. **超时控制**: 支持自定义响应超时时间
5. **错误处理**: 所有操作都有完整的异常处理机制

## 依赖

- pyserial: Python 串口通信库
- Flask: Web 框架

安装依赖：
```bash
pip install -r requirements.txt
```

