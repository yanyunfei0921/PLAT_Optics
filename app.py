import os
import sys
import json
from typing import final
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
sys.path.append(os.getenv('MVCAM_COMMON_RUNENV') + "/Samples/python/MvImport")
from MvCameraControl_class import MvCamera  # type: ignore
from core.cameraService import CameraService, VirtualCameraService
from core.sdiService import SDICameraService, SDI_AVAILABLE
from core.commandService import command_service
serial_service = command_service._serial
app = Flask(
    __name__,
    template_folder = rf"{os.getcwd()}/templates",
    static_folder = rf"{os.getcwd()}/static",
    static_url_path = '/static'
)

app.jinja_env.autoreload = True
app.jinja_env.variable_start_string = '?? --HUA-- <<'
app.jinja_env.variable_end_string = '>> --HUA-- ??'

STATIC_DIR = rf'{os.getcwd()}/static'
CONFIG_DIR = rf'{os.getcwd()}/config'

# 加载应用配置
APP_CONFIG_PATH = os.path.join(CONFIG_DIR, 'app_config.json')
_app_config = {}
try:
    if os.path.exists(APP_CONFIG_PATH):
        with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            _app_config = json.load(f)
except Exception as e:
    print(f"Warning: Failed to load app_config.json: {e}")

# 从配置文件获取服务器设置，提供默认值
SERVER_HOST = _app_config.get('server', {}).get('host', '127.0.0.1')
SERVER_PORT = _app_config.get('server', {}).get('port', 8090)
SERVER_DEBUG = _app_config.get('server', {}).get('debug', True)

# ========================Socket.IO 初始化===============================
socketio = SocketIO(app, cors_allowed_origins='*')

# 记录每个客户端的推流线程与相机选择
_client_stream_threads = {}
_client_camera_ids = {}

# 初始化测试箱内相机SDK
try:
    ret = MvCamera.MV_CC_Initialize()
    if ret != 0:
        print(f"SDK Init failed! ret[0x{ret:x}]")
    else:
        print("Camera SDK init success")
except Exception as e:
    print(f"SDK init Error: {e}")

# 测试箱内相机实例 (相机1和2为MvCamera硬件)
camSer1 = CameraService(0)
camSer2 = CameraService(1)
# SDI采集相机实例 (相机3为SDI输入)
sdiCam = SDICameraService(camera_id=3)
# 虚拟相机实例 (相机4为静态图像上传模式)
virtualCam = VirtualCameraService(camera_id=4)


def _get_camera_by_id(camera_id):
    """
    根据相机ID获取相机服务实例

    Args:
        camera_id:
            - 1, 2: MvCamera真实相机
            - 3: SDI采集相机
            - 4: 虚拟相机（静态图像上传）

    Returns:
        CameraService, SDICameraService 或 VirtualCameraService 实例
    """
    try:
        cam_id_int = int(camera_id)
    except Exception:
        cam_id_int = 1

    if cam_id_int == 1:
        return camSer1
    elif cam_id_int == 2:
        return camSer2
    elif cam_id_int == 3:
        return sdiCam
    elif cam_id_int == 4:
        return virtualCam
    else:
        return camSer1

def _stream_frames_to_client(camera_service, sid):
    while camera_service.running:
        frame_data = camera_service.getLatestFrame()
        if frame_data:
            socketio.emit('camera_frame', frame_data, room=sid)
        socketio.sleep(0.03)

# OK相机实例


if not os.path.exists(STATIC_DIR):
    os.mkdir(STATIC_DIR)
if not os.path.exists(CONFIG_DIR):
    os.mkdir(CONFIG_DIR)

# ========================页面加载路由==============================================

@app.route('/', methods = ["GET", "POST"])
def index():
    return render_template("index.html")

@app.route('/login', methods = ["GET", "POST"])
def login():
    return render_template("login.html")

@app.route('/serialSetting', methods=["GET"])
def serial_setting():
    return render_template("serialSetting.html")

@app.route('/opticalAxis', methods=["GET"])
def optical_axis():
    return render_template("opticalAxis.html")

@app.route('/laserDistance', methods=["GET"])
def laser_distance():
    return render_template("laserDistance.html")

@app.route('/dynamicTarget', methods=["GET"])
def dynamic_target():
    return render_template("dynamicTarget.html")

@app.route('/testRecord', methods=["GET"])
def test_record():
    return render_template("testRecord.html")

# =======================================================================

@app.route('/get-config', methods = ["GET", "POST"])
def get_config():
    """获取配置信息"""
    pass

# =========================serialSetting页面api==============================================
@app.route('/api/serial-config', methods=['GET'])
def get_serial_config():
    """获取串口配置"""
    config_path = os.path.join(CONFIG_DIR, 'serialConfig.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return jsonify({'success': True, 'data': config})
        else:
            return jsonify({'success': False, 'message': '配置文件不存在'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/serial-config', methods=['POST'])
def save_serial_config():
    """保存串口配置"""
    config_path = os.path.join(CONFIG_DIR, 'serialConfig.json')
    try:
        data = request.get_json()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True, 'message': '配置保存成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/serial/connect', methods=['POST'])
def connect_serial():
    """连接串口"""
    try:
        data = request.get_json()
        device_key = data.get('deviceKey')
        port = data.get('port')
        baudrate = data.get('baudrate', 9600)
        data_bits = data.get('dataBits', 8)
        stop_bits = data.get('stopBits', 1)
        parity = data.get('parity', 'None')
        timeout = data.get('timeout', 1000)
        
        success, message = serial_service.connect(
            device_key=device_key,
            port=port,
            baudrate=baudrate,
            data_bits=data_bits,
            stop_bits=stop_bits,
            parity=parity,
            timeout=timeout
        )
        
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/serial/disconnect', methods=['POST'])
def disconnect_serial():
    """断开串口连接"""
    try:
        data = request.get_json()
        device_key = data.get('deviceKey')
        
        success, message = serial_service.disconnect(device_key)
        
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/serial/connect-all', methods=['POST'])
def connect_all_serial():
    """连接所有设备"""
    try:
        devices_config = request.get_json()
        if not isinstance(devices_config, list):
            return jsonify({'success': False, 'message': '请发送设备配置列表'})
        
        # 调用串口服务的批量连接方法
        results = serial_service.connect_all(devices_config)
        
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/serial/disconnect-all', methods=['POST'])
def disconnect_all_serial():
    """断开所有串口连接"""
    try:
        results = serial_service.disconnect_all()
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})



@app.route('/api/serial/send-command', methods=['POST'])
def send_serial_command_raw():
    """发送指令到设备"""
    try:
        data = request.get_json()
        device_key = data.get('deviceKey')
        command = data.get('command')
        wait_response = data.get('waitResponse', True)
        response_timeout = data.get('responseTimeout', 2.0)
        
        # 发送二进制指令
        success, message, response_bytes = serial_service.send_command(
            device_key=device_key,
            command=command,  # 现在是字节串
            wait_response=wait_response,
            response_timeout=response_timeout
        )
        
        return jsonify({
            'success': success,
            'message': message,
            'response': response_bytes.hex(),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/serial/status', methods=['POST'])
def get_connection_status():
    """获取所有设备的连接状态"""
    try:
        devices_key = request.get_json()
        if not isinstance(devices_key, list):
            return jsonify({'success': False, 'message': '请发送设备键名列表'})
        
        status = serial_service.get_all_connection_status(devices_key)
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
# =========================================================================================

# =========================cameraService api - camearConfig wr part========================
@app.route('/api/camera-config', methods=['GET'])
def get_camera_config():
    """获取相机配置"""
    config_path = os.path.join(CONFIG_DIR, 'cameraConfig.json')
    try:
        if not os.path.exists(config_path):
            # 默认配置
            default_config = {
                "cameras": [
                    {"id": 1, "name": "相机1", "ip": "192.168.1.10", "exposureTime": 5000, "frameRate": 30, "threshold": 128},
                    {"id": 2, "name": "相机2", "ip": "192.168.1.11", "exposureTime": 5000, "frameRate": 30, "threshold": 128}
                ]
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            return jsonify({'success': True, 'data': default_config})
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/camera-config', methods=['POST'])
def save_camera_config():
    """保存相机配置"""
    config_path = os.path.join(CONFIG_DIR, 'cameraConfig.json')
    try:
        data = request.get_json()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True, 'message': '配置保存成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
# =========================================================================================

# =========================virtualCamera api (静态图像上传 - 相机4)===========================
@app.route('/api/virtual-camera/upload', methods=['POST'])
def upload_virtual_camera_image():
    """
    上传静态图像到虚拟相机(相机4)进行分析

    接受multipart/form-data格式的图像文件
    """
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': '未找到图像文件'})

        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        # 读取图像数据
        image_data = file.read()
        filename = file.filename

        # 使用虚拟相机处理图像
        result = virtualCam.uploadImage(image_data, filename)

        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/virtual-camera/reprocess', methods=['POST'])
def reprocess_virtual_camera_image():
    """重新处理虚拟相机当前图像 (参数变更后调用)"""
    try:
        result = virtualCam.reprocessImage()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/virtual-camera/frame', methods=['GET'])
def get_virtual_camera_frame():
    """获取虚拟相机最新帧"""
    try:
        frame_data = virtualCam.getLatestFrame()
        if frame_data:
            return jsonify({'success': True, 'frameData': frame_data})
        else:
            return jsonify({'success': False, 'message': '没有可用帧'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# =========================================================================================

# =========================SDI Camera api (相机3)============================================
@app.route('/api/sdi-camera/devices', methods=['GET'])
def get_sdi_devices():
    """获取SDI设备列表"""
    try:
        if not SDI_AVAILABLE:
            return jsonify({'success': False, 'message': 'SDI SDK不可用'})

        if not sdiCam._initialized:
            success, msg = sdiCam.initialize()
            if not success:
                return jsonify({'success': False, 'message': msg})

        devices = sdiCam.get_devices()
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/sdi-camera/params', methods=['GET'])
def get_sdi_params():
    """获取SDI相机当前参数"""
    try:
        params = sdiCam.getAllParams()
        return jsonify({'success': True, 'params': params})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/sdi-camera/params', methods=['POST'])
def set_sdi_params():
    """设置SDI相机参数"""
    try:
        data = request.get_json()
        results = {}

        if 'brightness' in data:
            results['brightness'] = sdiCam.setBrightness(int(data['brightness']))
        if 'contrast' in data:
            results['contrast'] = sdiCam.setContrast(int(data['contrast']))
        if 'saturation' in data:
            results['saturation'] = sdiCam.setSaturation(int(data['saturation']))
        if 'hue' in data:
            results['hue'] = sdiCam.setHue(int(data['hue']))
        if 'threshold' in data:
            results['threshold'] = sdiCam.setThreshold(int(data['threshold']))

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# =========================高级相机参数 API================================================
@app.route('/api/camera/all-params', methods=['POST'])
def get_all_camera_params():
    """获取相机所有参数"""
    try:
        data = request.get_json()
        camera_id = data.get('cameraId', 1)
        cam = _get_camera_by_id(camera_id)

        # 虚拟相机只返回基本参数
        if isinstance(cam, VirtualCameraService):
            params = {
                'threshold': cam.getThreshold(),
                'cameraType': 'virtual'
            }
            return jsonify({'success': True, 'params': params})

        # SDI相机返回SDI特有参数
        if isinstance(cam, SDICameraService):
            params = cam.getAllParams()
            params['cameraType'] = 'sdi'
            return jsonify({'success': True, 'params': params})

        # MvCamera真实相机需要连接后才能获取参数
        if cam.cam is None:
            return jsonify({'success': False, 'message': '相机未连接'})

        params = cam.getAllParams()
        params['cameraType'] = 'mvcamera'
        return jsonify({'success': True, 'params': params})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# =========================================================================================

# =========================commandService api==============================================
@app.route('/api/command/send', methods=['POST'])
def send_command():
    """发送指令"""
    try:
        data = request.get_json()
        device = data.get('device')
        cmd = data.get('cmd')
        params = data.get('params')
        wait_response = data.get('wait_response')
        timeout = data.get('timeout')
        success, message, response_bytes = command_service.send(device, cmd, params, wait_response=wait_response, timeout=timeout)
        return jsonify({'success': success, 'message': message, 'response': response_bytes.hex()})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/command/get-all-commands', methods=['GET'])
def get_all_commands():
    """获取所有指令"""
    commands = command_service.list_commands()  # 返回的是一个Dict
    return jsonify({'success': True, 'commands': commands})

# ==================================================================================


# =========================Socket.IO 事件============================================
@socketio.on('disconnect')
def handle_client_disconnect():
    """
    客户端断开连接时清理资源
    防止_client_stream_threads和_client_camera_ids内存泄漏
    """
    sid = request.sid
    camera_id = _client_camera_ids.pop(sid, None)

    # 清理推流线程记录
    _client_stream_threads.pop(sid, None)

    # 如果该客户端有绑定相机，尝试停止相机采集
    if camera_id is not None:
        try:
            cam = _get_camera_by_id(camera_id)
            if cam is not None and cam.running:
                if isinstance(cam, VirtualCameraService):
                    # 虚拟相机无需清理
                    pass
                elif isinstance(cam, SDICameraService):
                    # SDI相机断开
                    cam.disconnect()
                else:
                    # MvCamera断开
                    cam.closeAndDisconnectCamera()
                print(f"Client {sid} disconnected, camera {camera_id} stopped")
        except Exception as e:
            print(f"Error cleaning up camera {camera_id} for client {sid}: {e}")


@socketio.on('camera_connect')
def handle_camera_connect(data):
    """
    连接并开始采集
    data 需包含 cameraId:
        - 1, 2: MvCamera真实相机
        - 3: SDI采集相机
        - 4: 虚拟相机（静态图像上传）
    """
    try:
        camera_id = data.get('cameraId', 1)
        cam = _get_camera_by_id(camera_id)

        # 虚拟相机（相机4）不需要初始化SDK，直接返回成功
        if isinstance(cam, VirtualCameraService):
            _client_camera_ids[request.sid] = int(camera_id)
            emit('camera_connected', {
                'success': True,
                'cameraId': int(camera_id),
                'cameraType': 'virtual',
                'isVirtualCamera': True,
                'message': '虚拟相机已就绪，请上传图像文件'
            }, room=request.sid)
            return

        # SDI相机（相机3）初始化和连接
        if isinstance(cam, SDICameraService):
            if not SDI_AVAILABLE:
                emit('camera_error', {'success': False, 'message': 'SDI SDK不可用', 'cameraId': int(camera_id)}, room=request.sid)
                return

            sdi_channel = data.get('sdiChannel', 0)
            resolution_index = data.get('resolutionIndex', 0)

            success, msg = cam.connect(channel=sdi_channel, resolution_index=resolution_index)
            if not success:
                emit('camera_error', {'success': False, 'message': msg, 'cameraId': int(camera_id)}, room=request.sid)
                return

            # 记录客户端选择的相机
            _client_camera_ids[request.sid] = int(camera_id)

            # 启动向该客户端推流的后台任务
            def stream_sdi_frames(sdi_cam, sid):
                while sdi_cam.running:
                    frame_data = sdi_cam.getFrame()
                    if frame_data:
                        socketio.emit('camera_frame', frame_data, room=sid)
                    socketio.sleep(0.03)

            if request.sid in _client_stream_threads:
                pass
            _client_stream_threads[request.sid] = socketio.start_background_task(stream_sdi_frames, cam, request.sid)

            emit('camera_connected', {
                'success': True,
                'cameraId': int(camera_id),
                'cameraType': 'sdi',
                'isVirtualCamera': False,
                'message': 'SDI采集已连接'
            }, room=request.sid)
            return

        # MvCamera真实相机（相机1和2）：初始化并打开设备
        if not cam.initCamera():
            emit('camera_error', {'success': False, 'message': '初始化相机失败', 'cameraId': int(camera_id)}, room=request.sid)
            return
        if not cam.connectAndOpenCamera():
            emit('camera_error', {'success': False, 'message': '连接或开始采集失败', 'cameraId': int(camera_id)}, room=request.sid)
            return

        # 记录客户端选择的相机
        _client_camera_ids[request.sid] = int(camera_id)

        # 启动向该客户端推流的后台任务
        if request.sid in _client_stream_threads:
            # 已有线程则跳过或覆盖
            pass
        _client_stream_threads[request.sid] = socketio.start_background_task(_stream_frames_to_client, cam, request.sid)

        emit('camera_connected', {
            'success': True,
            'cameraId': int(camera_id),
            'cameraType': 'mvcamera',
            'isVirtualCamera': False
        }, room=request.sid)
    except Exception as e:
        emit('camera_error', {'success': False, 'message': str(e)}, room=request.sid)


@socketio.on('camera_disconnect')
def handle_camera_disconnect(data):
    """停止采集并断开连接，data 可包含 cameraId（可选，不传则用该连接最近一次选择）"""
    try:
        camera_id = data.get('cameraId') if isinstance(data, dict) else None
        if camera_id is None:
            camera_id = _client_camera_ids.get(request.sid)

        cam = _get_camera_by_id(camera_id) if camera_id is not None else None

        # 根据相机类型断开连接
        if cam is not None:
            if isinstance(cam, VirtualCameraService):
                # 虚拟相机不需要断开连接
                pass
            elif isinstance(cam, SDICameraService):
                # SDI相机断开连接
                cam.disconnect()
            else:
                # MvCamera断开连接
                cam.closeAndDisconnectCamera()

        # 清理该客户端记录
        _client_camera_ids.pop(request.sid, None)
        _client_stream_threads.pop(request.sid, None)

        emit('camera_disconnected', {'success': True, 'cameraId': int(camera_id) if camera_id is not None else None}, room=request.sid)
    except Exception as e:
        emit('camera_error', {'success': False, 'message': str(e)}, room=request.sid)

@socketio.on('camera_set_param')
def handle_camera_set_param(data):
    """
    设置相机参数
    data格式: {
        'cameraId': 1,
        'type': 参数类型,
        'value': 参数值
    }

    支持的参数类型:
    - 基础参数: exposureTime, frameRate, gain, threshold, imageMode
    - MvCamera高级参数 (相机1/2):
        - 图像尺寸: width, height, offsetX, offsetY
        - 图像处理: gamma, blackLevel, reverseX, reverseY
        - 触发控制: triggerMode, triggerSource, exposureAuto, gainAuto
    - SDI参数 (相机3):
        - 视频参数: brightness, contrast, saturation, hue
    """
    try:
        camera_id = data.get('cameraId', 1)
        param_type = data.get('type')
        value = data.get('value')

        cam = _get_camera_by_id(camera_id)

        # 虚拟相机（相机4）只支持 threshold 和 imageMode
        if isinstance(cam, VirtualCameraService):
            success = False
            message = ""

            if param_type == 'threshold':
                success = cam.setThreshold(value)
                message = "设置二值化阈值成功" if success else "设置二值化阈值失败"
            elif param_type == 'imageMode':
                is_binary = True if int(value) == 1 else False
                success = cam.setReturnBinaryMode(is_binary)
                mode_str = "二值化图" if is_binary else "原始灰度图"
                message = f"已切换至{mode_str}" if success else "切换显示模式失败"
            else:
                message = f"虚拟相机不支持参数: {param_type}"
                success = False

            if success:
                emit('camera_msg', {'success': True, 'message': message}, room=request.sid)
            else:
                emit('camera_error', {'success': False, 'message': message}, room=request.sid)
            return

        # SDI相机（相机3）支持特有参数
        if isinstance(cam, SDICameraService):
            success = False
            message = ""

            if param_type == 'threshold':
                success = cam.setThreshold(int(value))
                message = "设置二值化阈值成功" if success else "设置二值化阈值失败"
            elif param_type == 'imageMode':
                success = cam.setImageMode(int(value))
                mode_str = "二值化图" if int(value) == 1 else "原始图"
                message = f"已切换至{mode_str}" if success else "切换显示模式失败"
            elif param_type == 'brightness':
                success = cam.setBrightness(int(value))
                message = "设置亮度成功" if success else "设置亮度失败"
            elif param_type == 'contrast':
                success = cam.setContrast(int(value))
                message = "设置对比度成功" if success else "设置对比度失败"
            elif param_type == 'saturation':
                success = cam.setSaturation(int(value))
                message = "设置饱和度成功" if success else "设置饱和度失败"
            elif param_type == 'hue':
                success = cam.setHue(int(value))
                message = "设置色调成功" if success else "设置色调失败"
            else:
                message = f"SDI相机不支持参数: {param_type}"
                success = False

            if success:
                emit('camera_msg', {'success': True, 'message': message}, room=request.sid)
            else:
                emit('camera_error', {'success': False, 'message': message}, room=request.sid)
            return

        # MvCamera真实相机（相机1和2）：检查是否已连接
        if cam.cam is None:
            emit('camera_error', {'success': False, 'message': f'相机{camera_id}未连接，无法设置参数'}, room=request.sid)
            return

        success = False
        message = ""

        # 基础参数
        if param_type == 'exposureTime':
            success = cam.setExposureTime(float(value))
            message = "设置曝光时间成功" if success else "设置曝光时间失败"
        elif param_type == 'frameRate':
            success = cam.setAcquisitionFrameRate(float(value))
            message = "设置帧率成功" if success else "设置帧率失败"
        elif param_type == 'gain':
            success = cam.setGain(float(value))
            message = "设置增益成功" if success else "设置增益失败"
        elif param_type == 'threshold':
            success = cam.setThreshold(value)
            message = "设置二值化阈值成功" if success else "设置二值化阈值失败"
        elif param_type == 'imageMode':
            is_binary = True if int(value) == 1 else False
            success = cam.setReturnBinaryMode(is_binary)
            mode_str = "二值化图" if is_binary else "原始灰度图"
            message = f"已切换至{mode_str}" if success else "切换显示模式失败"

        # 高级参数 - 图像尺寸
        elif param_type == 'width':
            success = cam.setWidth(int(value))
            message = "设置宽度成功" if success else "设置宽度失败"
        elif param_type == 'height':
            success = cam.setHeight(int(value))
            message = "设置高度成功" if success else "设置高度失败"
        elif param_type == 'offsetX':
            success = cam.setOffsetX(int(value))
            message = "设置X偏移成功" if success else "设置X偏移失败"
        elif param_type == 'offsetY':
            success = cam.setOffsetY(int(value))
            message = "设置Y偏移成功" if success else "设置Y偏移失败"

        # 高级参数 - 图像处理
        elif param_type == 'gamma':
            success = cam.setGamma(float(value))
            message = "设置Gamma成功" if success else "设置Gamma失败"
        elif param_type == 'blackLevel':
            success = cam.setBlackLevel(float(value))
            message = "设置黑电平成功" if success else "设置黑电平失败"
        elif param_type == 'reverseX':
            success = cam.setReverseX(bool(value))
            message = "设置X镜像成功" if success else "设置X镜像失败"
        elif param_type == 'reverseY':
            success = cam.setReverseY(bool(value))
            message = "设置Y镜像成功" if success else "设置Y镜像失败"

        # 高级参数 - 触发控制
        elif param_type == 'triggerMode':
            success = cam.setTriggerMode(int(value))
            message = "设置触发模式成功" if success else "设置触发模式失败"
        elif param_type == 'triggerSource':
            success = cam.setTriggerSource(int(value))
            message = "设置触发源成功" if success else "设置触发源失败"
        elif param_type == 'exposureAuto':
            success = cam.setExposureAuto(int(value))
            message = "设置自动曝光成功" if success else "设置自动曝光失败"
        elif param_type == 'gainAuto':
            success = cam.setGainAuto(int(value))
            message = "设置自动增益成功" if success else "设置自动增益失败"
        elif param_type == 'softwareTrigger':
            success = cam.softwareTrigger()
            message = "软触发成功" if success else "软触发失败"

        else:
            message = f"未知参数类型: {param_type}"
            success = False

        if success:
            emit('camera_msg', {'success': True, 'message': message}, room=request.sid)
        else:
            emit('camera_error', {'success': False, 'message': message}, room=request.sid)

    except Exception as e:
        emit('camera_error', {'success': False, 'message': str(e)}, room=request.sid)


@socketio.on('camera_get_param')
def handle_camera_get_param(data):
    """
    获取相机参数
    data格式: {
        'cameraId': 1,
        'type': 参数类型
    }

    支持与 camera_set_param 相同的参数类型
    """
    try:
        camera_id = data.get('cameraId', 1)
        param_type = data.get('type')

        cam = _get_camera_by_id(camera_id)
        is_virtual = isinstance(cam, VirtualCameraService)

        # 虚拟相机只支持 threshold
        if is_virtual:
            if param_type == 'threshold':
                value = cam.getThreshold()
                emit('camera_param_value', {'success': True, 'type': param_type, 'value': value, 'cameraId': camera_id}, room=request.sid)
            else:
                emit('camera_error', {'success': False, 'message': f'虚拟相机不支持参数: {param_type}'}, room=request.sid)
            return

        # threshold 不需要相机连接
        if param_type == 'threshold':
            value = cam.getThreshold()
            emit('camera_param_value', {'success': True, 'type': param_type, 'value': value, 'cameraId': camera_id}, room=request.sid)
            return

        # 其他参数需要调用SDK，必须确保相机已连接
        if cam.cam is None:
            emit('camera_error', {'success': False, 'message': f'相机{camera_id}未连接，无法获取参数'}, room=request.sid)
            return

        value = None

        # 基础参数
        if param_type == 'exposureTime':
            value = cam.getExposureTime()
        elif param_type == 'frameRate':
            value = cam.getAcquisitionFrameRate()
        elif param_type == 'gain':
            value = cam.getGain()

        # 高级参数 - 图像尺寸
        elif param_type == 'width':
            value = cam.getWidth()
        elif param_type == 'height':
            value = cam.getHeight()
        elif param_type == 'offsetX':
            value = cam.getOffsetX()
        elif param_type == 'offsetY':
            value = cam.getOffsetY()

        # 高级参数 - 图像处理
        elif param_type == 'gamma':
            value = cam.getGamma()
        elif param_type == 'blackLevel':
            value = cam.getBlackLevel()
        elif param_type == 'reverseX':
            value = cam.getReverseX()
        elif param_type == 'reverseY':
            value = cam.getReverseY()

        # 高级参数 - 触发控制
        elif param_type == 'triggerMode':
            value = cam.getTriggerMode()
        elif param_type == 'triggerSource':
            value = cam.getTriggerSource()
        elif param_type == 'exposureAuto':
            value = cam.getExposureAuto()
        elif param_type == 'gainAuto':
            value = cam.getGainAuto()

        # 获取所有参数
        elif param_type == 'all':
            params = cam.getAllParams()
            emit('camera_param_value', {'success': True, 'type': 'all', 'value': params, 'cameraId': camera_id}, room=request.sid)
            return

        else:
            emit('camera_error', {'success': False, 'message': f"未知参数类型: {param_type}"}, room=request.sid)
            return

        if value is not None and value != -1:
            emit('camera_param_value', {'success': True, 'type': param_type, 'value': value, 'cameraId': camera_id}, room=request.sid)
        else:
            emit('camera_error', {'success': False, 'message': f"获取{param_type}失败"}, room=request.sid)

    except Exception as e:
        emit('camera_error', {'success': False, 'message': str(e)}, room=request.sid)

# ============================ main function ========================================
if __name__ == "__main__":
    try:
        print(f"Starting server at http://{SERVER_HOST}:{SERVER_PORT}")
        socketio.run(app, host=SERVER_HOST, port=SERVER_PORT, debug=SERVER_DEBUG)
    finally:
        MvCamera.MV_CC_Finalize()