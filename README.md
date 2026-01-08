# PLAT_Optics - 光电测试系统软件平台

基于 Flask + Vue 2.0 的光电测试系统软件平台，主要用于光轴一致性测试，支持工业相机控制、SDI视频采集和串口设备通信。

## 功能概述

| 模块 | 功能说明 |
|------|---------|
| 光轴一致性测试 | 质心提取、偏移计算、光轴中心校准、测试记录保存 |
| 动态目标模拟 | 电机控制、目标运动模拟 |
| 激光模拟测距 | 延时模块控制、距离模拟计算 |
| 激光能量测试 | 使用外部激光能量计测量 |
| 测试记录 | 串口日志、光轴测试记录查询与导出(Excel/PDF) |

## 系统要求

- Python 3.8+
- Windows OS
- MvCamera SDK (海康威视 MVS)
- HWS SDK (SDI采集卡)

## 安装

### 1. Python依赖

```bash
pip install -r requirements.txt
```

### 2. MvCamera SDK

安装海康威视MVS软件，确保环境变量已设置：
```
MVCAM_COMMON_RUNENV = "C:/Program Files (x86)/MVS/Development"
```

### 3. SDI采集卡SDK

SDI采集卡所需的DLL文件已包含在 `core/sdi/` 目录中，无需额外安装。

### 4. 离线部署

前端依赖(Vue.js、Axios、Element UI、Socket.IO)已包含在 `static/jsscripts/`，运行时无需网络连接。

离线安装Python包：
```bash
# 联网机器下载
pip download -r requirements.txt -d ./packages

# 离线机器安装
pip install --no-index --find-links=./packages -r requirements.txt
```

## 配置

配置文件位于 `config/` 目录：

| 文件 | 说明 | 是否可修改 |
|------|------|-----------|
| `app_config.json` | 服务器地址、端口、调试模式 | 可修改 |
| `cameraConfig.json` | 相机参数(曝光、增益、光轴中心等) | 可修改 |
| `serialConfig.json` | 串口设备配置(端口、波特率) | 硬件相关 |
| `commandConfig.json` | 设备指令模板 | 硬件相关 |

### 服务器配置 (app_config.json)

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8090,
    "debug": true
  }
}
```

局域网访问需将 `host` 改为 `"0.0.0.0"`。

### 光轴中心校准 (cameraConfig.json)

每个相机可单独配置光轴中心，用于偏移计算和十字线绘制的基准点：

```json
{
  "opticalAxisCenterX": -1,
  "opticalAxisCenterY": -1
}
```

- `-1`: 使用图像中心 `(width-1)/2` 作为默认值
- `>=0`: 使用指定的像素坐标作为光轴中心

可在"相机设置 → 默认配置 → 光轴中心设置"中修改。

## 运行

### 方式1：使用启动脚本（推荐）

双击运行 `start.bat`，脚本会自动：
- 激活虚拟环境 `.venv`
- 启动服务

### 方式2：手动运行

```bash
# 激活虚拟环境
.venv\Scripts\activate

# 启动服务
python app.py
```

服务启动后访问 `http://127.0.0.1:8090`（或配置的地址）。

## 项目结构

```
PLAT_Optics/
├── app.py                  # Flask主程序
├── requirements.txt        # Python依赖
├── config/                 # 配置文件
│   ├── app_config.json     # 服务器配置
│   ├── cameraConfig.json   # 相机参数
│   ├── serialConfig.json   # 串口配置
│   └── commandConfig.json  # 指令模板
├── core/                   # 核心服务模块
│   ├── cameraService.py    # MVS相机服务
│   ├── sdiService.py       # SDI采集卡服务
│   ├── serialService.py    # 串口通信服务
│   ├── commandService.py   # 指令模板引擎
│   ├── databaseService.py  # 数据库服务(SQLite)
│   └── sdi/                # SDI SDK及DLL
├── data/                   # 数据存储
│   ├── test_records.db     # SQLite数据库
│   └── images/             # 测试图像
├── static/                 # 静态资源
│   └── jsscripts/          # 前端JS库
└── templates/              # HTML模板
    ├── index.html          # 主界面
    ├── login.html          # 登录页
    ├── opticalAxis.html    # 光轴一致性测试
    ├── dynamicTarget.html  # 动态目标模拟
    ├── laserDistance.html  # 激光模拟测距
    ├── laserEnergy.html    # 激光能量测试
    ├── serialSetting.html  # 串口设置
    └── testRecord.html     # 测试记录
```

## 硬件支持

### 相机设备

| 类型 | SDK | 说明 |
|------|-----|------|
| MVS工业相机 x2 | MvCamera SDK | GigE Vision协议 |
| SDI采集卡 x1 | HWS SDK | 视频采集 |
| 虚拟相机 | - | 静态图像分析 |

### 串口设备

| 设备 | 功能 |
|------|------|
| 光源控制器 | 指示激光功率、可见光功率、黑体温度 |
| 三轴电机控制器 | 水平/垂直/旋转轴位置控制 |
| 延时模块 | 激光测距延时控制 |
| 导轨电机 | 导轨位置控制 |

## API接口

### REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/serial-config` | GET/POST | 串口配置 |
| `/api/serial/connect` | POST | 连接串口设备 |
| `/api/serial/disconnect` | POST | 断开串口设备 |
| `/api/command/send` | POST | 发送设备指令 |
| `/api/camera-config` | GET/POST | 相机配置 |
| `/api/tests/optical-axis` | GET/POST | 光轴测试记录 |
| `/api/export/optical-test/<id>/pdf` | GET | 导出PDF报告 |

### WebSocket事件

| 事件 | 方向 | 说明 |
|------|------|------|
| `camera_connect` | C→S | 连接相机并开始推流 |
| `camera_disconnect` | C→S | 断开相机 |
| `camera_set_param` | C→S | 设置相机参数 |
| `camera_frame` | S→C | 推送相机帧数据 |

## 故障排除

### 相机无法检测

1. 检查网络连接（GigE相机使用以太网）
2. 确认MVS SDK已安装且环境变量 `MVCAM_COMMON_RUNENV` 已设置
3. 使用MVS客户端软件验证相机可访问

### SDI采集卡无信号

1. 检查SDI视频源是否正常输出
2. 确认 `core/sdi/` 目录下DLL文件完整
3. 检查采集通道配置

### 串口连接失败

1. 检查 `serialConfig.json` 中的COM端口号
2. 确认波特率等参数正确
3. 确保端口未被其他程序占用

## 许可

内部使用。
