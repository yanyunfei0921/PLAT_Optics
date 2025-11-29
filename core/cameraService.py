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
    def __init__(self, nConnectionNum):
        self.deviceList = None
        self.nConnectionNum = nConnectionNum
        self.tlayerType = (MV_GIGE_DEVICE)
        self.cam = None
        self.hwnd = None    #测试用显示窗口句柄
        self.winName = "testDisplayWin"
        self.stFloatValue = None    #浮点类型值
        self.running = False    #是否在传输
        self.threshold = 128
        self.frame_queue = deque(maxlen=2) #图像队列
        self.hThreadHandle = None

    def initCamera(self):
        # init 和 destory 这两个SDK相关函数改为在app.py文件中调用，而这里仅保留单个相机的创建和销毁
        # MvCamera.MV_CC_Initialize()

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
            print ("intput error!")
            return False

        # 直接窗口显示代码
        # DEBUG        
        # cv2.namedWindow(self.winName, cv2.WINDOW_NORMAL)
        # cv2.resizeWindow(self.winName, 1280, 1024)
        # self.hwnd = ctypes.windll.user32.FindWindowW(None, self.winName)
        # if not self.hwnd:
        #     print("error: find hwnd failed")
        #     return False
        # DEBUG END

        self.stFloatValue = MVCC_FLOATVALUE()

        return True

    def connectAndOpenCamera(self):
        self.cam = MvCamera()
        stDeviceList = cast(self.deviceList.pDeviceInfo[int(self.nConnectionNum)], POINTER(MV_CC_DEVICE_INFO)).contents
        ret = self.cam.MV_CC_CreateHandle(stDeviceList)
        if ret != 0:
            print ("create handle fail! ret[0x%x]" % ret)
            return False
        
        ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != 0:
            print ("open device fail! ret[0x%x]" % ret)
            return False
        
        if stDeviceList.nTLayerType == MV_GIGE_DEVICE:
            nPacketSize = self.cam.MV_CC_GetOptimalPacketSize()
            if int(nPacketSize) > 0:
                ret = self.cam.MV_CC_SetIntValue("GevSCPSPacketSize",nPacketSize)
                if ret != 0:
                    print ("Warning: Set Packet Size fail! ret[0x%x]" % ret)
            else:
                print ("Warning: Get Packet Size fail! ret[0x%x]" % nPacketSize)
        
        ret = self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
        if ret != 0:
            print ("set trigger mode fail! ret[0x%x]" % ret)
            return False
        
        ret = self.cam.MV_CC_SetEnumValue("ExposureAuto", 0)
        if ret != 0:
            print("set exposure auto off fail! ret[0x%x]" % ret)
            return False

        # ret = self.cam.MV_CC_SetGrabStrategy(LatestImagesOnly)
        # if ret != 0:
        #     print("set grab strategy fail! ret[0x%x]" % ret)
        #     return False

        ret = self.cam.MV_CC_StartGrabbing()
        if ret != 0:
            print ("start grabbing fail! ret[0x%x]" % ret)
            return False

        try:
            self.running = True
            self.hThreadHandle = threading.Thread(target=self.work_thread, args=(None, None))
            self.hThreadHandle.start()
        except:
            self.running = False
            print("error: unable to start thread")

        return True

    def closeAndDisconnectCamera(self):
        self.running = False

        if hasattr(self, 'hThreadHandle') and self.hThreadHandle.is_alive():
            self.hThreadHandle.join()
        
        ret = self.cam.MV_CC_StopGrabbing()
        if ret != 0:
            print ("stop grabbing fail! ret[0x%x]" % ret)
            return False
        
        ret = self.cam.MV_CC_CloseDevice()
        if ret != 0:
            print ("close device fail! ret[0x%x]" % ret)
            return False
        
        ret = self.cam.MV_CC_DestroyHandle()
        if ret != 0:
            print ("destroy handle fail! ret[0x%x]" % ret)
            return False
        
        # MvCamera.MV_CC_Finalize()

        return True

    def work_thread(self, pData=0, nDataSize=0):
        stOutFrame = MV_FRAME_OUT()  
        memset(byref(stOutFrame), 0, sizeof(stOutFrame))
        while self.running:
            ret = self.cam.MV_CC_GetImageBuffer(stOutFrame, 1000)
            if None != stOutFrame.pBufAddr and 0 == ret:
                # print ("get one frame: Width[%d], Height[%d], nFrameNum[%d]"  % (stOutFrame.stFrameInfo.nWidth, stOutFrame.stFrameInfo.nHeight, stOutFrame.stFrameInfo.nFrameNum))
                
                # DEBUG
                # 最初用于直接窗口显示图像的代码
                # displayimage = MV_CC_IMAGE()
                # displayimage.nWidth = stOutFrame.stFrameInfo.nWidth 
                # displayimage.nHeight =  stOutFrame.stFrameInfo.nHeight 
                # displayimage.enPixelType =  stOutFrame.stFrameInfo.enPixelType 
                # displayimage.pImageBuf = stOutFrame.pBufAddr
                # displayimage.nImageBuffSize = stOutFrame.stFrameInfo.nFrameLen
                # displayimage.nImageLen =    stOutFrame.stFrameInfo.nFrameLen
                # ret = self.cam.MV_CC_DisplayOneFrameEx2(int(self.hwnd),displayimage, 0)
                # if ret != 0:
                #     print ("MV_CC_DisplayOneFrameEx2 fail! ret[0x%x]" % ret)
                # DEBUG END

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
                    ret = self.cam.MV_CC_ConvertPixelTypeEx(stConvertParam)
                    if ret != 0:
                        print("convert pixel to mono8 fail! ret[0x%x]" % ret)
                    else:
                        img = np.ctypeslib.as_array(stConvertParam.pDstBuffer, shape=(stConvertParam.nHeight, stConvertParam.nWidth))

                if img is None:
                    print("error: img is None!")
                    return

                frame_data = self.centroidExtract(img, stOutFrame.stFrameInfo.nFrameNum)
                if frame_data:
                    self.frame_queue.append(frame_data)
                else:
                    print("error: frame_data is None!")

                nRet = self.cam.MV_CC_FreeImageBuffer(stOutFrame)
                if nRet != 0:
                    print("free image buffer fail! ret[0x%x]" % nRet)
            else:
                print ("no data[0x%x]" % ret)
                time.sleep(0.01)

    def setAcquisitionFrameRate(self, rate):
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

    def setExpsureTime(self, time):
        ret = self.cam.MV_CC_SetFloatValue("ExpsureTime", time)
        if ret != 0:
            print("set expsure time fail! ret[0x%x]" % ret)
            return False
        return True
    
    def getExpsureTime(self):
        memset(byref(self.stFloatValue), 0 ,sizeof(MVCC_FLOATVALUE))
        ret = self.cam.MV_CC_GetFloatValue("ExpsureTime", self.stFloatValue)
        if ret != 0:
            print("get expsure time fail! ret[0x%x]" % ret)
            return -1
        return self.stFloatValue.fCurValue

    def setGain(self, gain):
        ret = self.cam.MV_CC_SetFloatValue("Gain", gain)
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

    def centroidExtract(self, gray_image, frame_num):
        th = int(self.threshold)
        _, binary = cv2.threshold(gray_image, th, 255, cv2.THRESH_BINARY)
        mask = binary > 0
        if np.any(mask):
            ys, xs = np.nonzero(mask)
            intensities = gray_image[ys, xs].astype(np.float64)
            wsum = intensities.sum()
            cx = (xs * intensities).sum() / wsum
            cy = (ys * intensities).sum() / wsum
        else:
            cx, cy = -1.0, -1.0

        ok, buf = cv2.imencode('.jpg', gray_image)
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

    def getLatestFrame(self):
        return self.frame_queue.pop() if self.frame_queue else None


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