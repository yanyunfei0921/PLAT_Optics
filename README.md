# PLAT_Optics - Photoelectric Test Platform

Flask + Vue 2.0 based photoelectric test platform for industrial camera control and serial device communication.

## Requirements

- Python 3.8+
- MvCamera SDK (Hikvision MVS)
- Windows OS

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. MvCamera SDK Setup

Ensure the MVS SDK is installed and the environment variable is set:

```
MVCAM_COMMON_RUNENV = "C:/Program Files (x86)/MVS/Development"
```

### 3. Offline Installation

All frontend dependencies (Vue.js, Axios, Element UI, Socket.IO) are included locally in `static/jsscripts/`. No internet connection is required at runtime.

For pip packages in offline environments:
```bash
# On a machine with internet, download packages:
pip download -r requirements.txt -d ./packages

# On the offline machine, install from local packages:
pip install --no-index --find-links=./packages -r requirements.txt
```

## Configuration

Configuration files are located in the `config/` directory:

| File | Description |
|------|-------------|
| `app_config.json` | Server host, port, and debug settings |
| `serialConfig.json` | Serial device configurations (fixed by hardware) |
| `cameraConfig.json` | Camera parameters (exposure, gain, etc.) |
| `commandConfig.json` | Command templates for serial devices (fixed by hardware) |

### Server Configuration (app_config.json)

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8090,
    "debug": true
  }
}
```

To allow LAN access, change `host` to `"0.0.0.0"`.

## Running the Application

```bash
python app.py
```

The server will start at `http://127.0.0.1:8090` (or as configured).

## Project Structure

```
PLAT_Optics/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── config/                 # Configuration files
│   ├── app_config.json     # Server settings
│   ├── serialConfig.json   # Serial device configs
│   ├── cameraConfig.json   # Camera parameters
│   └── commandConfig.json  # Command templates
├── core/                   # Hardware interface modules
│   ├── cameraService.py    # MvCamera SDK wrapper
│   ├── serialService.py    # Serial communication
│   └── commandService.py   # Command template engine
├── static/                 # Static assets
│   ├── jsscripts/          # Frontend JS libraries
│   ├── images/             # Images
│   └── configs/            # (Legacy location, use config/ instead)
└── templates/              # HTML templates
    ├── index.html          # Main dashboard
    ├── login.html          # Login page
    ├── serialSetting.html  # Serial device configuration
    └── opticalAxis.html    # Optical axis testing
```

## Features

- Real-time camera streaming via WebSocket
- Centroid calculation for optical alignment
- Serial device control (light source, motors, delay module)
- Binary/grayscale image mode switching
- Camera parameter adjustment (exposure, gain, frame rate)

## Hardware Support

### Cameras
- GigE Vision cameras via MvCamera SDK (Hikvision/MVS)

### Serial Devices
- Light source controller
- Three-axis motor controller
- Delay module
- Rail motor

## API Endpoints

### REST API
- `GET/POST /api/serial-config` - Serial configuration
- `POST /api/serial/connect` - Connect serial device
- `POST /api/serial/disconnect` - Disconnect serial device
- `POST /api/command/send` - Send command to device
- `GET/POST /api/camera-config` - Camera configuration

### WebSocket Events
- `camera_connect` - Connect and start camera streaming
- `camera_disconnect` - Stop camera streaming
- `camera_set_param` - Set camera parameters
- `camera_frame` - Receive camera frames (server to client)

## Troubleshooting

### Camera not detected
1. Check network connection (GigE cameras use Ethernet)
2. Verify MVS SDK is installed and `MVCAM_COMMON_RUNENV` is set
3. Use MVS software to verify camera is accessible

### Serial device connection failed
1. Check COM port number in `serialConfig.json`
2. Verify baud rate and other serial parameters
3. Ensure no other application is using the COM port

## License

Internal use only.
