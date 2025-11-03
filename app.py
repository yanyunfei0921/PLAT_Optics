import os
import json
from flask import Flask, render_template, request, jsonify
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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8090, debug=True)