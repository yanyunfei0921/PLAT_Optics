"""
数据库服务 - 用于测试记录的存储和查询
使用SQLite数据库，支持串口日志和光轴测试记录
"""
import sqlite3
import os
import json
import base64
from datetime import datetime
from typing import Optional, Dict, List, Any
import threading

class DatabaseService:
    _instance = None
    _lock = threading.Lock()

    # 串口日志最大保留条数
    MAX_SERIAL_LOGS = 1000

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        # 数据目录
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, 'data')
        self.images_dir = os.path.join(self.data_dir, 'images')
        self.db_path = os.path.join(self.data_dir, 'test_records.db')

        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

        # 初始化数据库
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """初始化数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 创建串口日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS serial_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                device TEXT,
                port TEXT,
                command TEXT,
                params TEXT,
                cmd_bytes TEXT,
                response_bytes TEXT,
                success INTEGER,
                message TEXT
            )
        ''')

        # 创建光轴测试记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS optical_axis_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                operator TEXT,
                base_camera_id INTEGER,
                base_camera_name TEXT,
                base_image_path TEXT,
                base_width INTEGER,
                base_height INTEGER,
                base_centroid_x REAL,
                base_centroid_y REAL,
                base_focal_length REAL,
                base_pixel_size REAL,
                base_offset_x REAL,
                base_offset_y REAL,
                test_camera_id INTEGER,
                test_camera_name TEXT,
                test_image_path TEXT,
                test_width INTEGER,
                test_height INTEGER,
                test_centroid_x REAL,
                test_centroid_y REAL,
                test_focal_length REAL,
                test_pixel_size REAL,
                test_offset_x REAL,
                test_offset_y REAL,
                remark TEXT
            )
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_serial_logs_timestamp ON serial_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_serial_logs_device ON serial_logs(device)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_optical_tests_time ON optical_axis_tests(test_time)')

        # 数据库迁移：为旧表添加 operator 字段
        try:
            cursor.execute('ALTER TABLE optical_axis_tests ADD COLUMN operator TEXT')
        except:
            pass  # 字段已存在则忽略

        conn.commit()
        conn.close()

    # ==================== 串口日志方法 ====================

    def log_serial_command(self, device: str, port: str, command: str,
                          params: Dict = None, cmd_bytes: bytes = None,
                          response_bytes: bytes = None, success: bool = True,
                          message: str = None) -> int:
        """
        记录串口指令

        Args:
            device: 设备名称
            port: 串口号
            command: 指令名称
            params: 指令参数字典
            cmd_bytes: 发送的字节
            response_bytes: 返回的字节
            success: 是否成功
            message: 结果消息

        Returns:
            插入记录的ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO serial_logs (device, port, command, params, cmd_bytes,
                                    response_bytes, success, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            device,
            port,
            command,
            json.dumps(params, ensure_ascii=False) if params else None,
            cmd_bytes.hex() if cmd_bytes else None,
            response_bytes.hex() if response_bytes else None,
            1 if success else 0,
            message
        ))

        log_id = cursor.lastrowid
        conn.commit()

        # 自动清理旧记录
        self._cleanup_serial_logs(conn)

        conn.close()
        return log_id

    def _cleanup_serial_logs(self, conn: sqlite3.Connection):
        """清理超出限制的串口日志，保留最近的记录"""
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM serial_logs')
        count = cursor.fetchone()[0]

        if count > self.MAX_SERIAL_LOGS:
            # 删除最早的记录
            delete_count = count - self.MAX_SERIAL_LOGS
            cursor.execute('''
                DELETE FROM serial_logs WHERE id IN (
                    SELECT id FROM serial_logs ORDER BY id ASC LIMIT ?
                )
            ''', (delete_count,))
            conn.commit()

    def get_serial_logs(self, device: str = None, port: str = None,
                       start_time: str = None, end_time: str = None,
                       limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        查询串口日志

        Args:
            device: 设备筛选
            port: 串口筛选
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            日志列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM serial_logs WHERE 1=1'
        params = []

        if device:
            query += ' AND device = ?'
            params.append(device)
        if port:
            query += ' AND port = ?'
            params.append(port)
        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)

        query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 获取总数
        count_query = 'SELECT COUNT(*) FROM serial_logs WHERE 1=1'
        count_params = []
        if device:
            count_query += ' AND device = ?'
            count_params.append(device)
        if port:
            count_query += ' AND port = ?'
            count_params.append(port)
        if start_time:
            count_query += ' AND timestamp >= ?'
            count_params.append(start_time)
        if end_time:
            count_query += ' AND timestamp <= ?'
            count_params.append(end_time)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]

        conn.close()

        return {
            'logs': [dict(row) for row in rows],
            'total': total
        }

    def delete_serial_log(self, log_id: int) -> bool:
        """删除单条串口日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM serial_logs WHERE id = ?', (log_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def clear_serial_logs(self) -> int:
        """清空所有串口日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM serial_logs')
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected

    # ==================== 光轴测试记录方法 ====================

    def save_image(self, image_data: bytes, prefix: str = 'optical') -> str:
        """
        保存图片到文件系统

        Args:
            image_data: 图片二进制数据
            prefix: 文件名前缀

        Returns:
            图片相对路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f'{prefix}_{timestamp}.png'
        filepath = os.path.join(self.images_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(image_data)

        # 返回相对路径
        return f'data/images/{filename}'

    def save_image_base64(self, base64_data: str, prefix: str = 'optical') -> str:
        """
        保存base64编码的图片

        Args:
            base64_data: base64编码的图片数据 (可带data:image前缀)
            prefix: 文件名前缀

        Returns:
            图片相对路径
        """
        # 移除data:image/xxx;base64,前缀
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]

        image_data = base64.b64decode(base64_data)
        return self.save_image(image_data, prefix)

    def save_optical_test(self, data: Dict) -> int:
        """
        保存光轴测试记录

        Args:
            data: 测试数据字典，包含所有字段

        Returns:
            记录ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO optical_axis_tests (
                operator,
                base_camera_id, base_camera_name, base_image_path,
                base_width, base_height, base_centroid_x, base_centroid_y,
                base_focal_length, base_pixel_size, base_offset_x, base_offset_y,
                test_camera_id, test_camera_name, test_image_path,
                test_width, test_height, test_centroid_x, test_centroid_y,
                test_focal_length, test_pixel_size, test_offset_x, test_offset_y,
                remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('operator'),
            data.get('base_camera_id'),
            data.get('base_camera_name'),
            data.get('base_image_path'),
            data.get('base_width'),
            data.get('base_height'),
            data.get('base_centroid_x'),
            data.get('base_centroid_y'),
            data.get('base_focal_length'),
            data.get('base_pixel_size'),
            data.get('base_offset_x'),
            data.get('base_offset_y'),
            data.get('test_camera_id'),
            data.get('test_camera_name'),
            data.get('test_image_path'),
            data.get('test_width'),
            data.get('test_height'),
            data.get('test_centroid_x'),
            data.get('test_centroid_y'),
            data.get('test_focal_length'),
            data.get('test_pixel_size'),
            data.get('test_offset_x'),
            data.get('test_offset_y'),
            data.get('remark')
        ))

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return record_id

    def update_optical_test(self, test_id: int, data: Dict) -> bool:
        """
        更新光轴测试记录（用于补充测试光轴数据）

        Args:
            test_id: 记录ID
            data: 要更新的字段

        Returns:
            是否成功
        """
        if not data:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        # 构建动态UPDATE语句
        fields = []
        values = []
        for key, value in data.items():
            fields.append(f'{key} = ?')
            values.append(value)

        values.append(test_id)

        query = f'UPDATE optical_axis_tests SET {", ".join(fields)} WHERE id = ?'
        cursor.execute(query, values)

        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def get_optical_tests(self, start_time: str = None, end_time: str = None,
                         limit: int = 50, offset: int = 0) -> Dict:
        """
        查询光轴测试记录

        Args:
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            包含记录列表和总数的字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM optical_axis_tests WHERE 1=1'
        params = []

        if start_time:
            query += ' AND test_time >= ?'
            params.append(start_time)
        if end_time:
            query += ' AND test_time <= ?'
            params.append(end_time)

        query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 获取总数
        count_query = 'SELECT COUNT(*) FROM optical_axis_tests WHERE 1=1'
        count_params = []
        if start_time:
            count_query += ' AND test_time >= ?'
            count_params.append(start_time)
        if end_time:
            count_query += ' AND test_time <= ?'
            count_params.append(end_time)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]

        conn.close()

        return {
            'records': [dict(row) for row in rows],
            'total': total
        }

    def get_optical_test(self, test_id: int) -> Optional[Dict]:
        """获取单条光轴测试记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM optical_axis_tests WHERE id = ?', (test_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_optical_test(self, test_id: int) -> bool:
        """删除光轴测试记录（同时删除关联图片）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 先获取图片路径
        cursor.execute('SELECT base_image_path, test_image_path FROM optical_axis_tests WHERE id = ?', (test_id,))
        row = cursor.fetchone()

        if row:
            # 删除图片文件
            for path in [row['base_image_path'], row['test_image_path']]:
                if path:
                    full_path = os.path.join(self.base_dir, path)
                    if os.path.exists(full_path):
                        try:
                            os.remove(full_path)
                        except:
                            pass

            # 删除记录
            cursor.execute('DELETE FROM optical_axis_tests WHERE id = ?', (test_id,))
            conn.commit()

        affected = cursor.rowcount
        conn.close()
        return affected > 0


# 全局实例
db_service = DatabaseService()
