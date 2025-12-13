import sys
import time
import cv2
import numpy as np

# 尝试导入刚刚编译好的模块
try:
    import ok_camera
except ImportError:
    print("错误：无法导入 ok_camera 模块。请确保编译成功且 .pyd 文件在当前目录下。")
    sys.exit(1)

def main():
    # 1. 实例化相机
    print("[Python] 正在初始化相机对象...")
    cam = ok_camera.Camera()

    # 2. 打开相机
    # 注意：根据之前的 C++ 代码，这里会自动启用"内部条纹模拟"
    if not cam.open():
        print("[Python] 打开相机失败！请检查采集卡驱动或硬件连接。")
        return

    print("[Python] 相机打开成功！")

    # 3. 设置参数 (可选，测试一下接口是否通)
    cam.set_exposure(20000) # 设置 20ms
    print("[Python] 曝光已设置。")

    # 4. 开始采集
    if not cam.start():
        print("[Python] 启动采集失败！")
        cam.close()
        return
    
    print("[Python] 开始采集。按 'q' 键退出...")

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            # 5. 获取图像 (这是 Numpy 数组)
            # 这里的 get_image 是线程安全的，直接从 C++ 队列取数
            image = cam.get_image()

            # 检查图像是否有效 (size > 0 表示有数据)
            if image is not None and image.size > 0:
                # 统计帧率
                frame_count += 1
                
                # OK卡通常出来的是 RGB，OpenCV 显示需要 BGR，做个转换
                # 如果颜色看起来很怪（比如人脸变蓝），说明需要这一步转换
                bgr_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                
                # 在图像上打印帧号
                cv2.putText(bgr_image, f"Frame: {frame_count}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                # 显示图像
                cv2.imshow('OK Camera Live (Test Pattern)', bgr_image)

            else:
                # 如果队列为空，稍微睡一下避免死循环占用 CPU
                # 实际生产中可以不睡，直接 continue，取决于对 CPU 的容忍度
                time.sleep(0.001)

            # 按 'q' 退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[Python] 用户强制中断")

    finally:
        # 6. 计算平均帧率
        end_time = time.time()
        elapsed = end_time - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"[Python] 采集结束。平均帧率: {fps:.2f} FPS")

        # 7. 清理资源
        cam.stop()
        cam.close()
        cv2.destroyAllWindows()
        print("[Python] 资源已释放。")

if __name__ == "__main__":
    main()