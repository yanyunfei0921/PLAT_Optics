import os
import sys
import time
import threading
import cv2
import base64
import queue
import numpy as np
from collections import deque
from ctypes import *
sys.path.append(os.getenv('MVCAM_COMMON_RUNENV') + "/Samples/python/MvImport")
from MvCameraControl_class import *  # type: ignore


class CameraService:
    """
    相机服务类 - 管理MvCamera SDK相机的连接、采集和图像处理

    支持GigE Vision工业相机，提供帧采集、质心计算和实时流推送功能。
    支持通过设备索引或IP地址连接相机。
    """

    def __init__(self, nConnectionNum: int, camera_ip: str = None):
        """
        初始化相机服务

        Args:
            nConnectionNum: 相机设备索引号(从0开始)，用于枚举方式连接
            camera_ip: 相机IP地址(可选)，用于按IP查找设备
        """
        self.deviceList = None
        self.nConnectionNum = nConnectionNum
        self.camera_ip = camera_ip  # 目标相机IP地址
        self.tlayerType = MV_GIGE_DEVICE
        self.cam = None
        self.stFloatValue = None
        self.running = False
        self.threshold = 128
        self.median_kernel_size = 0  # 中值滤波核大小，0表示不滤波
        self.return_binary_image = False
        self.frame_queue = deque(maxlen=2)
        self.hThreadHandle = None

    def setCameraIp(self, ip: str):
        """设置相机IP地址"""
        self.camera_ip = ip

    def initCameraByIp(self, camera_ip: str = None) -> bool:
        """
        通过IP地址初始化相机 - 枚举设备并找到匹配IP的相机

        Args:
            camera_ip: 相机IP地址 (如 "192.168.1.10")

        Returns:
            bool: 初始化成功返回True，失败返回False
        """
        if camera_ip:
            self.camera_ip = camera_ip

        if not self.camera_ip:
            print("Error: No camera IP specified")
            return False

        # 枚举所有设备
        self.deviceList = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(self.tlayerType, self.deviceList)
        if ret != 0:
            print(f"enum devices fail! ret[0x{ret:x}]")
            return False

        if self.deviceList.nDeviceNum == 0:
            print("find no device!")
            return False

        print(f"Find {self.deviceList.nDeviceNum} devices!")

        # 遍历设备，找到匹配IP的设备
        target_ip_parts = self.camera_ip.split('.')
        target_ip_int = (int(target_ip_parts[0]) << 24) | (int(target_ip_parts[1]) << 16) | \
                        (int(target_ip_parts[2]) << 8) | int(target_ip_parts[3])

        found_index = -1
        for i in range(self.deviceList.nDeviceNum):
            mvcc_dev_info = cast(self.deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
            if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE:
                device_ip = mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp
                nip1 = (device_ip >> 24) & 0xFF
                nip2 = (device_ip >> 16) & 0xFF
                nip3 = (device_ip >> 8) & 0xFF
                nip4 = device_ip & 0xFF
                device_ip_str = f"{nip1}.{nip2}.{nip3}.{nip4}"

                strModeName = ''.join([chr(c) for c in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName if c != 0])
                print(f"  Device [{i}]: {strModeName}, IP: {device_ip_str}")

                if device_ip == target_ip_int:
                    found_index = i
                    print(f"  -> Found target camera at index {i}!")

        if found_index == -1:
            print(f"Error: Camera with IP {self.camera_ip} not found in enumerated devices!")
            return False

        self.nConnectionNum = found_index
        self.stFloatValue = MVCC_FLOATVALUE()
        return True

    def initCamera(self) -> bool:
        """
        初始化相机 - 枚举设备并选择指定索引的相机

        Returns:
            bool: 初始化成功返回True，失败返回False
        """
        self.deviceList = MV_CC_DEVICE_INFO_LIST()
    
        ret = MvCamera.MV_CC_EnumDevices(self.tlayerType, self.deviceList)
        if ret != 0:
            print ("enum devices fail! ret[0x%x]" % ret)
            return False
        
        if self.deviceList.nDeviceNum == 0:
            print ("find no device!")
            return False

        print("Find %d devices!" % self.deviceList.nDeviceNum)

        for i in range(self.deviceList.nDeviceNum):
            mvcc_dev_info = cast(self.deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
            if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE:
                print("\ngige device: [%d]" % i)
                strModeName = ''.join([chr(c) for c in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName if c != 0])
                print("device model name: %s" % strModeName)

                nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
                nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
                nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
                nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                print("current ip: %d.%d.%d.%d\n" % (nip1, nip2, nip3, nip4))

        # self.nConnectionNum = input("please input the number of the device to connect:")

        if int(self.nConnectionNum) >= self.deviceList.nDeviceNum:
            print("input error!")
            return False

        self.stFloatValue = MVCC_FLOATVALUE()

        return True

    def connectAndOpenCamera(self) -> bool:
        """
        连接并打开相机 - 创建句柄、打开设备并开始采集

        Returns:
            bool: 成功返回True，失败返回False
        """
        if self.cam is not None:
            self.closeAndDisconnectCamera()

        if self.deviceList is None:
            print("Error: deviceList is None, please call initCamera() or initCameraByIp() first")
            return False

        self.cam = MvCamera()
        stDeviceList = cast(self.deviceList.pDeviceInfo[int(self.nConnectionNum)], POINTER(MV_CC_DEVICE_INFO)).contents
        ret = self.cam.MV_CC_CreateHandle(stDeviceList)
        if ret != 0:
            print(f"create handle fail! ret[0x{ret:x}]")
            self.cam = None
            return False

        ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != 0:
            print(f"open device fail! ret[0x{ret:x}]")
            self.cam.MV_CC_DestroyHandle()
            self.cam = None
            return False

        if stDeviceList.nTLayerType == MV_GIGE_DEVICE:
            nPacketSize = self.cam.MV_CC_GetOptimalPacketSize()
            if int(nPacketSize) > 0:
                ret = self.cam.MV_CC_SetIntValue("GevSCPSPacketSize", nPacketSize)
                if ret != 0:
                    print(f"Warning: Set Packet Size fail! ret[0x{ret:x}]")
            else:
                print(f"Warning: Get Packet Size fail! ret[0x{nPacketSize:x}]")

        ret = self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
        if ret != 0:
            print(f"set trigger mode fail! ret[0x{ret:x}]")
            return False

        ret = self.cam.MV_CC_SetEnumValue("ExposureAuto", 0)
        if ret != 0:
            print(f"set exposure auto off fail! ret[0x{ret:x}]")
            return False

        ret = self.cam.MV_CC_StartGrabbing()
        if ret != 0:
            print(f"start grabbing fail! ret[0x{ret:x}]")
            return False

        try:
            self.running = True
            self.hThreadHandle = threading.Thread(target=self.work_thread, args=(None, None))
            self.hThreadHandle.start()
        except RuntimeError as e:
            self.running = False
            print(f"error: unable to start thread - {e}")
        except Exception as e:
            self.running = False
            print(f"error: unexpected error starting thread - {e}")

        return True

    def closeAndDisconnectCamera(self) -> bool:
        """
        关闭并断开相机 - 停止采集、关闭设备并销毁句柄

        Returns:
            bool: 成功返回True
        """
        self.running = False
        if self.cam is None:
            return True
        
        try:
            ret = self.cam.MV_CC_StopGrabbing()
            if ret != 0:
                print ("stop grabbing fail! ret[0x%x]" % ret)
        except Exception as e:
             print(f"StopGrabbing exception: {e}")
            
        if hasattr(self, 'hThreadHandle') and self.hThreadHandle is not None:
            if self.hThreadHandle.is_alive():
                # 给线程一点时间退出，通常 StopGrabbing 后它是秒退的
                # 超时时间设为 2.0s，足以覆盖 1FPS 的极端情况
                self.hThreadHandle.join(timeout=2.0) 
            self.hThreadHandle = None      
        
        try:
            ret = self.cam.MV_CC_CloseDevice()
            if ret != 0:
                print ("close device fail! ret[0x%x]" % ret)
        except Exception as e:
            print(f"CloseDevice exception: {e}")
        
        try:
            ret = self.cam.MV_CC_DestroyHandle()
            if ret != 0:
                print ("destroy handle fail! ret[0x%x]" % ret)
        except Exception as e:
            print(f"DestroyHandle exception: {e}")
        
        # MvCamera.MV_CC_Finalize()
        self.cam = None
        return True

    def work_thread(self, pData=0, nDataSize=0):
        stOutFrame = MV_FRAME_OUT()  
        memset(byref(stOutFrame), 0, sizeof(stOutFrame))
        while self.running:
            ret = self.cam.MV_CC_GetImageBuffer(stOutFrame, 2000)
            if None != stOutFrame.pBufAddr and 0 == ret:
                if not self.running:
                    self.cam.MV_CC_FreeImageBuffer(stOutFrame)
                    break

                nWidth = stOutFrame.stFrameInfo.nWidth
                nHeight = stOutFrame.stFrameInfo.nHeight
                src_pixel_type = stOutFrame.stFrameInfo.enPixelType

                img = None

                if src_pixel_type == PixelType_Gvsp_Mono8:
                    # 已经是Mono8，不必转换
                    pData = cast(stOutFrame.pBufAddr, POINTER(c_ubyte))
                    img = np.ctypeslib.as_array(pData, shape=(nHeight, nWidth))
                else:
                    # 需要转换为Mono8
                    nMonoSize = nWidth * nHeight
                    stConvertParam = MV_CC_PIXEL_CONVERT_PARAM_EX()
                    memset(byref(stConvertParam), 0, sizeof(stConvertParam))
                    stConvertParam.nWidth = nWidth
                    stConvertParam.nHeight = nHeight
                    stConvertParam.pSrcData = stOutFrame.pBufAddr
                    stConvertParam.nSrcDataLen = stOutFrame.stFrameInfo.nFrameLen
                    stConvertParam.enSrcPixelType = src_pixel_type
                    stConvertParam.enDstPixelType = PixelType_Gvsp_Mono8
                    stConvertParam.pDstBuffer = (c_ubyte * nMonoSize)()
                    stConvertParam.nDstBufferSize = nMonoSize
                    if self.running:
                        ret = self.cam.MV_CC_ConvertPixelTypeEx(stConvertParam)
                        if ret != 0:
                            print("convert pixel to mono8 fail! ret[0x%x]" % ret)
                        else:
                            img = np.ctypeslib.as_array(stConvertParam.pDstBuffer, shape=(stConvertParam.nHeight, stConvertParam.nWidth))
                
                if img is not None and self.running:
                    frame_data = self.centroidExtract(img, stOutFrame.stFrameInfo.nFrameNum)
                    if frame_data:
                        self.frame_queue.append(frame_data)
                    else:
                        print("error: frame_data is None!")

                nRet = self.cam.MV_CC_FreeImageBuffer(stOutFrame)
                if nRet != 0:
                    print("free image buffer fail! ret[0x%x]" % nRet)
            else:
                if ret == 0x80000007:
                    # 超时无数据
                    continue
                if not self.running:
                    break

                print (f"GetImageBuffer failed: ret[0x{ret:x}]")
                time.sleep(0.01)

    def setAcquisitionFrameRate(self, rate):
        ret = self.cam.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", True)
        if ret != 0:
            print("Warning: Set AcquisitionFrameRateEnable fail! ret[0x%x]" % ret)
        ret = self.cam.MV_CC_SetFloatValue("AcquisitionFrameRate", rate)
        if ret != 0:
            print("set frame fail! ret[0x%x]" % ret)
            return False
        return True
    
    def getAcquisitionFrameRate(self):
        memset(byref(self.stFloatValue), 0 ,sizeof(MVCC_FLOATVALUE))
        ret = self.cam.MV_CC_GetFloatValue("AcquisitionFrameRate", self.stFloatValue)
        if ret != 0:
            print ("get AcquisitionFrameRate value fail! nRet [0x%x]" % ret)
            return -1
        return self.stFloatValue.fCurValue

    def setExposureTime(self, time):
        self.cam.MV_CC_SetEnumValue("ExposureAuto", 0)
        ret = self.cam.MV_CC_SetFloatValue("ExposureTime", time)
        if ret != 0:
            print("set exposure time fail! ret[0x%x]" % ret)
            return False
        return True

    def getExposureTime(self):
        memset(byref(self.stFloatValue), 0, sizeof(MVCC_FLOATVALUE))
        ret = self.cam.MV_CC_GetFloatValue("ExposureTime", self.stFloatValue)
        if ret != 0:
            print("get exposure time fail! ret[0x%x]" % ret)
            return -1
        return self.stFloatValue.fCurValue

    def setGain(self, gain):
        self.cam.MV_CC_SetEnumValue("GainAuto", 0)
        ret = self.cam.MV_CC_SetFloatValue("Gain", float(gain))
        if ret != 0:
            print("set gain fail! ret[0x%x]" % ret)
            return False
        return True
    
    def getGain(self):
        memset(byref(self.stFloatValue), 0 ,sizeof(MVCC_FLOATVALUE))
        ret = self.cam.MV_CC_GetFloatValue("Gain", self.stFloatValue)
        if ret != 0:
            print("get gain fail! ret[0x%x]" % ret)
            return -1
        return self.stFloatValue.fCurValue

    def setThreshold(self, threshold):
        threshold = int(threshold)
        if threshold < 0:
            threshold = 0
        if threshold > 255:
            threshold = 255
        self.threshold = threshold
        return True

    def getThreshold(self):
        return self.threshold

    def setMedianKernelSize(self, size):
        """设置中值滤波核大小，0表示不滤波，必须为奇数"""
        size = int(size)
        if size < 0:
            size = 0
        if size > 0 and size % 2 == 0:
            size += 1  # 确保是奇数
        if size > 31:
            size = 31  # 限制最大值
        self.median_kernel_size = size
        return True

    def getMedianKernelSize(self):
        return self.median_kernel_size

    def centroidExtract(self, gray_image: np.ndarray, frame_num: int) -> dict:
        """
        提取图像质心并编码为JPEG

        使用cv2.moments()计算强度加权质心，比numpy循环更快。
        阈值以下的像素被设为0，质心基于阈值以上像素的灰度强度加权计算。

        Args:
            gray_image: 灰度图像 (Mono8)
            frame_num: 帧编号

        Returns:
            dict: 包含图像base64、尺寸、质心坐标等信息，失败返回None
        """
        # 应用中值滤波（如果设置了）
        if self.median_kernel_size > 0:
            gray_image = cv2.medianBlur(gray_image, self.median_kernel_size)

        th = int(self.threshold)
        _, binary = cv2.threshold(gray_image, th, 255, cv2.THRESH_BINARY)

        # 创建掩码图像：阈值以下像素设为0，保留原始灰度值用于加权计算
        # 使用cv2.moments()计算强度加权质心，C优化比numpy循环更快
        masked = np.where(binary > 0, gray_image, 0).astype(np.float64)
        M = cv2.moments(masked)

        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        else:
            cx, cy = -1.0, -1.0

        target_image = binary if self.return_binary_image else gray_image
        ok, buf = cv2.imencode('.jpg', target_image)
        if ok:
            image_base64 = base64.b64encode(buf.tobytes()).decode('ascii')
        else:
            image_base64 = ''
            print("error: encode fail!")
            return None

        nHeight, nWidth = gray_image.shape[:2]
        cam_id = int(self.nConnectionNum) + 1

        frame_data = {
            'image': f'data:image/jpeg;base64,{image_base64}',
            'width': int(nWidth),
            'height': int(nHeight),
            'centroidX': float(cx),
            'centroidY': float(cy),
            'frameNum': int(frame_num),
            'cameraId': cam_id
        }

        return frame_data

    def setReturnBinaryMode(self, is_binary):
        """设置是否返回二值化图像"""
        self.return_binary_image = bool(is_binary)
        # print(f"Camera [{self.nConnectionNum}] return binary mode: {self.return_binary_image}")
        return True

    def getLatestFrame(self):
        return self.frame_queue.pop() if self.frame_queue else None

    # ======================== 高级参数设置方法 ========================

    def getWidth(self) -> int:
        """获取图像宽度"""
        stIntValue = MVCC_INTVALUE_EX()
        memset(byref(stIntValue), 0, sizeof(stIntValue))
        ret = self.cam.MV_CC_GetIntValueEx("Width", stIntValue)
        if ret != 0:
            print(f"get Width fail! ret[0x{ret:x}]")
            return -1
        return stIntValue.nCurValue

    def setWidth(self, width: int) -> bool:
        """设置图像宽度"""
        ret = self.cam.MV_CC_SetIntValueEx("Width", int(width))
        if ret != 0:
            print(f"set Width fail! ret[0x{ret:x}]")
            return False
        return True

    def getHeight(self) -> int:
        """获取图像高度"""
        stIntValue = MVCC_INTVALUE_EX()
        memset(byref(stIntValue), 0, sizeof(stIntValue))
        ret = self.cam.MV_CC_GetIntValueEx("Height", stIntValue)
        if ret != 0:
            print(f"get Height fail! ret[0x{ret:x}]")
            return -1
        return stIntValue.nCurValue

    def setHeight(self, height: int) -> bool:
        """设置图像高度"""
        ret = self.cam.MV_CC_SetIntValueEx("Height", int(height))
        if ret != 0:
            print(f"set Height fail! ret[0x{ret:x}]")
            return False
        return True

    def getOffsetX(self) -> int:
        """获取X偏移"""
        stIntValue = MVCC_INTVALUE_EX()
        memset(byref(stIntValue), 0, sizeof(stIntValue))
        ret = self.cam.MV_CC_GetIntValueEx("OffsetX", stIntValue)
        if ret != 0:
            print(f"get OffsetX fail! ret[0x{ret:x}]")
            return -1
        return stIntValue.nCurValue

    def setOffsetX(self, offset: int) -> bool:
        """设置X偏移"""
        ret = self.cam.MV_CC_SetIntValueEx("OffsetX", int(offset))
        if ret != 0:
            print(f"set OffsetX fail! ret[0x{ret:x}]")
            return False
        return True

    def getOffsetY(self) -> int:
        """获取Y偏移"""
        stIntValue = MVCC_INTVALUE_EX()
        memset(byref(stIntValue), 0, sizeof(stIntValue))
        ret = self.cam.MV_CC_GetIntValueEx("OffsetY", stIntValue)
        if ret != 0:
            print(f"get OffsetY fail! ret[0x{ret:x}]")
            return -1
        return stIntValue.nCurValue

    def setOffsetY(self, offset: int) -> bool:
        """设置Y偏移"""
        ret = self.cam.MV_CC_SetIntValueEx("OffsetY", int(offset))
        if ret != 0:
            print(f"set OffsetY fail! ret[0x{ret:x}]")
            return False
        return True

    def getGamma(self) -> float:
        """获取Gamma值"""
        memset(byref(self.stFloatValue), 0, sizeof(MVCC_FLOATVALUE))
        ret = self.cam.MV_CC_GetFloatValue("Gamma", self.stFloatValue)
        if ret != 0:
            print(f"get Gamma fail! ret[0x{ret:x}]")
            return -1.0
        return self.stFloatValue.fCurValue

    def setGamma(self, gamma: float) -> bool:
        """设置Gamma值"""
        # 先启用Gamma
        self.cam.MV_CC_SetBoolValue("GammaEnable", True)
        ret = self.cam.MV_CC_SetFloatValue("Gamma", float(gamma))
        if ret != 0:
            print(f"set Gamma fail! ret[0x{ret:x}]")
            return False
        return True

    def getBlackLevel(self) -> float:
        """获取黑电平"""
        memset(byref(self.stFloatValue), 0, sizeof(MVCC_FLOATVALUE))
        ret = self.cam.MV_CC_GetFloatValue("BlackLevel", self.stFloatValue)
        if ret != 0:
            print(f"get BlackLevel fail! ret[0x{ret:x}]")
            return -1.0
        return self.stFloatValue.fCurValue

    def setBlackLevel(self, level: float) -> bool:
        """设置黑电平"""
        ret = self.cam.MV_CC_SetFloatValue("BlackLevel", float(level))
        if ret != 0:
            print(f"set BlackLevel fail! ret[0x{ret:x}]")
            return False
        return True

    def getReverseX(self) -> bool:
        """获取X镜像状态"""
        bValue = c_bool(False)
        ret = self.cam.MV_CC_GetBoolValue("ReverseX", bValue)
        if ret != 0:
            print(f"get ReverseX fail! ret[0x{ret:x}]")
            return False
        return bValue.value

    def setReverseX(self, enable: bool) -> bool:
        """设置X镜像"""
        ret = self.cam.MV_CC_SetBoolValue("ReverseX", bool(enable))
        if ret != 0:
            print(f"set ReverseX fail! ret[0x{ret:x}]")
            return False
        return True

    def getReverseY(self) -> bool:
        """获取Y镜像状态"""
        bValue = c_bool(False)
        ret = self.cam.MV_CC_GetBoolValue("ReverseY", bValue)
        if ret != 0:
            print(f"get ReverseY fail! ret[0x{ret:x}]")
            return False
        return bValue.value

    def setReverseY(self, enable: bool) -> bool:
        """设置Y镜像"""
        ret = self.cam.MV_CC_SetBoolValue("ReverseY", bool(enable))
        if ret != 0:
            print(f"set ReverseY fail! ret[0x{ret:x}]")
            return False
        return True

    def getTriggerMode(self) -> int:
        """获取触发模式 (0=Off, 1=On)"""
        stEnumValue = MVCC_ENUMVALUE()
        memset(byref(stEnumValue), 0, sizeof(stEnumValue))
        ret = self.cam.MV_CC_GetEnumValue("TriggerMode", stEnumValue)
        if ret != 0:
            print(f"get TriggerMode fail! ret[0x{ret:x}]")
            return -1
        return stEnumValue.nCurValue

    def setTriggerMode(self, mode: int) -> bool:
        """设置触发模式 (0=Off, 1=On)"""
        ret = self.cam.MV_CC_SetEnumValue("TriggerMode", int(mode))
        if ret != 0:
            print(f"set TriggerMode fail! ret[0x{ret:x}]")
            return False
        return True

    def getTriggerSource(self) -> int:
        """获取触发源"""
        stEnumValue = MVCC_ENUMVALUE()
        memset(byref(stEnumValue), 0, sizeof(stEnumValue))
        ret = self.cam.MV_CC_GetEnumValue("TriggerSource", stEnumValue)
        if ret != 0:
            print(f"get TriggerSource fail! ret[0x{ret:x}]")
            return -1
        return stEnumValue.nCurValue

    def setTriggerSource(self, source: int) -> bool:
        """设置触发源 (0=Line0, 1=Line1, 7=Software)"""
        ret = self.cam.MV_CC_SetEnumValue("TriggerSource", int(source))
        if ret != 0:
            print(f"set TriggerSource fail! ret[0x{ret:x}]")
            return False
        return True

    def softwareTrigger(self) -> bool:
        """软触发一次"""
        ret = self.cam.MV_CC_SetCommandValue("TriggerSoftware")
        if ret != 0:
            print(f"software trigger fail! ret[0x{ret:x}]")
            return False
        return True

    def getExposureAuto(self) -> int:
        """获取自动曝光模式 (0=Off, 1=Once, 2=Continuous)"""
        stEnumValue = MVCC_ENUMVALUE()
        memset(byref(stEnumValue), 0, sizeof(stEnumValue))
        ret = self.cam.MV_CC_GetEnumValue("ExposureAuto", stEnumValue)
        if ret != 0:
            print(f"get ExposureAuto fail! ret[0x{ret:x}]")
            return -1
        return stEnumValue.nCurValue

    def setExposureAuto(self, mode: int) -> bool:
        """设置自动曝光模式 (0=Off, 1=Once, 2=Continuous)"""
        ret = self.cam.MV_CC_SetEnumValue("ExposureAuto", int(mode))
        if ret != 0:
            print(f"set ExposureAuto fail! ret[0x{ret:x}]")
            return False
        return True

    def getGainAuto(self) -> int:
        """获取自动增益模式 (0=Off, 1=Once, 2=Continuous)"""
        stEnumValue = MVCC_ENUMVALUE()
        memset(byref(stEnumValue), 0, sizeof(stEnumValue))
        ret = self.cam.MV_CC_GetEnumValue("GainAuto", stEnumValue)
        if ret != 0:
            print(f"get GainAuto fail! ret[0x{ret:x}]")
            return -1
        return stEnumValue.nCurValue

    def setGainAuto(self, mode: int) -> bool:
        """设置自动增益模式 (0=Off, 1=Once, 2=Continuous)"""
        ret = self.cam.MV_CC_SetEnumValue("GainAuto", int(mode))
        if ret != 0:
            print(f"set GainAuto fail! ret[0x{ret:x}]")
            return False
        return True

    def getAllParams(self) -> dict:
        """获取所有参数的当前值"""
        params = {
            'width': self.getWidth(),
            'height': self.getHeight(),
            'offsetX': self.getOffsetX(),
            'offsetY': self.getOffsetY(),
            'exposureTime': self.getExposureTime(),
            'exposureAuto': self.getExposureAuto(),
            'gain': self.getGain(),
            'gainAuto': self.getGainAuto(),
            'frameRate': self.getAcquisitionFrameRate(),
            'gamma': self.getGamma(),
            'blackLevel': self.getBlackLevel(),
            'reverseX': self.getReverseX(),
            'reverseY': self.getReverseY(),
            'triggerMode': self.getTriggerMode(),
            'threshold': self.getThreshold(),
        }
        return params

    def saveFeatureFile(self, filename: str) -> bool:
        """保存相机配置到文件"""
        ret = self.cam.MV_CC_FeatureSave(filename)
        if ret != 0:
            print(f"save feature fail! ret[0x{ret:x}]")
            return False
        return True

    def loadFeatureFile(self, filename: str) -> bool:
        """从文件加载相机配置"""
        ret = self.cam.MV_CC_FeatureLoad(filename)
        if ret != 0:
            print(f"load feature fail! ret[0x{ret:x}]")
            return False
        return True


class VirtualCameraService:
    """
    虚拟相机服务类 - 用于静态图像上传和分析

    不连接实际硬件，允许用户上传本地图像文件进行质心计算等分析。
    """

    def __init__(self, camera_id: int = 3):
        """
        初始化虚拟相机服务

        Args:
            camera_id: 虚拟相机ID (默认为3)
        """
        self.camera_id = camera_id
        self.running = False
        self.threshold = 128
        self.median_kernel_size = 0  # 中值滤波核大小，0表示不滤波
        self.return_binary_image = False
        self.current_image = None
        self.frame_queue = deque(maxlen=2)
        self.frame_num = 0
        self.cam = None  # 用于兼容性检查

    def uploadImage(self, image_data: bytes, filename: str = "") -> dict:
        """
        上传图像文件

        Args:
            image_data: 图像二进制数据
            filename: 文件名

        Returns:
            dict: 包含处理结果的字典
        """
        try:
            # 从字节数据解码图像
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img is None:
                return {'success': False, 'message': '无法解析图像文件'}

            self.current_image = img
            self.frame_num += 1

            # 计算质心并生成帧数据
            frame_data = self.centroidExtract(img, self.frame_num)
            if frame_data:
                self.frame_queue.append(frame_data)
                return {'success': True, 'message': '图像上传成功', 'frameData': frame_data}
            else:
                return {'success': False, 'message': '图像处理失败'}

        except Exception as e:
            return {'success': False, 'message': f'上传失败: {str(e)}'}

    def centroidExtract(self, gray_image: np.ndarray, frame_num: int) -> dict:
        """
        提取图像质心并编码为JPEG (与CameraService保持一致)
        """
        # 应用中值滤波（如果设置了）
        if self.median_kernel_size > 0:
            gray_image = cv2.medianBlur(gray_image, self.median_kernel_size)

        th = int(self.threshold)
        _, binary = cv2.threshold(gray_image, th, 255, cv2.THRESH_BINARY)

        masked = np.where(binary > 0, gray_image, 0).astype(np.float64)
        M = cv2.moments(masked)

        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        else:
            cx, cy = -1.0, -1.0

        target_image = binary if self.return_binary_image else gray_image
        ok, buf = cv2.imencode('.jpg', target_image)
        if ok:
            image_base64 = base64.b64encode(buf.tobytes()).decode('ascii')
        else:
            return None

        nHeight, nWidth = gray_image.shape[:2]

        frame_data = {
            'image': f'data:image/jpeg;base64,{image_base64}',
            'width': int(nWidth),
            'height': int(nHeight),
            'centroidX': float(cx),
            'centroidY': float(cy),
            'frameNum': int(frame_num),
            'cameraId': self.camera_id
        }

        return frame_data

    def setThreshold(self, threshold: int) -> bool:
        """设置二值化阈值"""
        threshold = int(threshold)
        if threshold < 0:
            threshold = 0
        if threshold > 255:
            threshold = 255
        self.threshold = threshold
        # 如果有当前图像，重新处理
        if self.current_image is not None:
            self.frame_num += 1
            frame_data = self.centroidExtract(self.current_image, self.frame_num)
            if frame_data:
                self.frame_queue.append(frame_data)
        return True

    def getThreshold(self) -> int:
        """获取二值化阈值"""
        return self.threshold

    def setMedianKernelSize(self, size: int) -> bool:
        """设置中值滤波核大小，0表示不滤波，必须为奇数"""
        size = int(size)
        if size < 0:
            size = 0
        if size > 0 and size % 2 == 0:
            size += 1  # 确保是奇数
        if size > 31:
            size = 31  # 限制最大值
        self.median_kernel_size = size
        # 如果有当前图像，重新处理
        if self.current_image is not None:
            self.frame_num += 1
            frame_data = self.centroidExtract(self.current_image, self.frame_num)
            if frame_data:
                self.frame_queue.append(frame_data)
        return True

    def getMedianKernelSize(self) -> int:
        """获取中值滤波核大小"""
        return self.median_kernel_size

    def setReturnBinaryMode(self, is_binary: bool) -> bool:
        """设置是否返回二值化图像"""
        self.return_binary_image = bool(is_binary)
        # 如果有当前图像，重新处理
        if self.current_image is not None:
            self.frame_num += 1
            frame_data = self.centroidExtract(self.current_image, self.frame_num)
            if frame_data:
                self.frame_queue.append(frame_data)
        return True

    def getLatestFrame(self) -> dict:
        """获取最新帧"""
        return self.frame_queue.pop() if self.frame_queue else None

    def reprocessImage(self) -> dict:
        """重新处理当前图像 (用于参数变更后)"""
        if self.current_image is None:
            return {'success': False, 'message': '没有已上传的图像'}

        self.frame_num += 1
        frame_data = self.centroidExtract(self.current_image, self.frame_num)
        if frame_data:
            self.frame_queue.append(frame_data)
            return {'success': True, 'frameData': frame_data}
        return {'success': False, 'message': '图像处理失败'}


if __name__ == "__main__":
    # 测试相机
    camSer = CameraService(0)
    if not camSer.initCamera():
        print("init camera failed")
        sys.exit()

    if not camSer.connectAndOpenCamera():
        print("connect and open camera failed")
        sys.exit()

    print("按q退出")
    try:
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
    except KeyboardInterrupt:
        print("中断退出")
    finally:
        camSer.closeAndDisconnectCamera()