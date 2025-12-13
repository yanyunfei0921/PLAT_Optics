import os
import sys
import json
from typing import final
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
sys.path.append(os.getenv('MVCAM_COMMON_RUNENV') + "/Samples/python/MvImport")
from MvCameraControl_class import MvCamera  # type: ignore
from core.cameraService import CameraService
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
CONFIG_DIR = rf'{os.getcwd()}/static/configs'

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

# 测试箱内相机实例
camSer1 = CameraService(0)
camSer2 = CameraService(1)
def _get_camera_by_id(camera_id):
    try:
        cam_id_int = int(camera_id)
    except Exception:
        cam_id_int = 1
    return camSer1 if cam_id_int == 1 else camSer2

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
@socketio.on('camera_connect')
def handle_camera_connect(data):
    """连接并开始采集，data 需包含 cameraId: 1 或 2"""
    try:
        camera_id = data.get('cameraId', 1)
        cam = _get_camera_by_id(camera_id)

        # 初始化并打开设备（包含开始抓取）
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

        emit('camera_connected', {'success': True, 'cameraId': int(camera_id)}, room=request.sid)
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
        if cam is not None:
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
        'type': 'exposureTime' | 'frameRate' | 'threshold' | 'gain', 
        'value': 5000
    }
    """
    try:
        camera_id = data.get('cameraId', 1)
        param_type = data.get('type')
        value = data.get('value')
        
        cam = _get_camera_by_id(camera_id)
        
        # 检查相机是否已连接 (句柄是否存在)
        if cam.cam is None:
             emit('camera_error', {'success': False, 'message': f'相机{camera_id}未连接，无法设置参数'}, room=request.sid)
             return
            
        success = False
        message = ""

        if param_type == 'exposureTime':
            success = cam.setExpsureTime(float(value))
            message = "设置曝光时间成功" if success else "设置曝光时间失败"
        elif param_type == 'frameRate':
            success = cam.setAcquisitionFrameRate(float(value))
            message = "设置帧率成功" if success else "设置帧率失败"
        elif param_type == 'gain':
             success = cam.setGain(float(value))
             message = "设置增益成功" if success else "设置增益失败"
        elif param_type == 'threshold':
            # 阈值是纯软件参数，不涉及SDK底层指令，直接设置类属性
            cam.threshold = int(value)
            success = True
            message = "设置二值化阈值成功"
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
        'type': 'exposureTime' | 'frameRate' | 'threshold' | 'gain'
    }
    """
    try:
        camera_id = data.get('cameraId', 1)
        param_type = data.get('type')
        
        cam = _get_camera_by_id(camera_id)
        
        # 阈值是本地变量，理论上不需要相机连接也能获取默认值，但为了统一逻辑，还是检查一下或直接返回类属性
        if param_type == 'threshold':
            value = cam.threshold
            emit('camera_param_value', {'success': True, 'type': param_type, 'value': value, 'cameraId': camera_id}, room=request.sid)
            return

        # 其他参数需要调用SDK，必须确保相机已连接
        if cam.cam is None:
             emit('camera_error', {'success': False, 'message': f'相机{camera_id}未连接，无法获取参数'}, room=request.sid)
             return

        value = -1
        
        if param_type == 'exposureTime':
            value = cam.getExpsureTime()
        elif param_type == 'frameRate':
            value = cam.getAcquisitionFrameRate()
        elif param_type == 'gain':
            value = cam.getGain()
        else:
             emit('camera_error', {'success': False, 'message': f"未知参数类型: {param_type}"}, room=request.sid)
             return
        
        if value != -1:
             emit('camera_param_value', {'success': True, 'type': param_type, 'value': value, 'cameraId': camera_id}, room=request.sid)
        else:
             emit('camera_error', {'success': False, 'message': f"获取{param_type}失败"}, room=request.sid)

    except Exception as e:
        emit('camera_error', {'success': False, 'message': str(e)}, room=request.sid)

# ============================ main function ========================================
if __name__ == "__main__":
    try:
        socketio.run(app, host="127.0.0.1", port=8090, debug=True)
    finally:
        MvCamera.MV_CC_Finalize()