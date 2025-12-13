#include "OKCamera.h"
#include <iostream>
#include <vector>

// 全局实例指针，供静态回调使用
OKCamera* g_pCameraInstance = nullptr;

OKCamera::OKCamera() 
    : m_hBoard(NULL), m_pWorkBuffer(nullptr), m_pFrameQueue(nullptr),
      m_lWidth(0), m_lHeight(0), m_bIsCapturing(false),
      m_bIsSoftwareMock(false), m_nSimFrameIndex(0)
{
    g_pCameraInstance = this;
    // 初始化队列，最大长度设为 2 (模拟 Python deque(maxlen=2))
    m_pFrameQueue = new SafeFrameQueue(2);
}

OKCamera::~OKCamera()
{
    Close();
    if (m_pFrameQueue) delete m_pFrameQueue;
}

bool OKCamera::Open()
{
    if (m_hBoard != NULL) return true;

    MLONG lIndex = -1;
    // 1. 尝试打开物理采集卡
    m_hBoard = okOpenBoard(&lIndex);

    if (m_hBoard != NULL) {
        // --- 场景 A: 检测到采集卡 (Hardware Mock) ---
        std::cout << "[OKCamera] 硬件就绪。启用采集卡内部动态条纹模拟..." << std::endl;
        
        // 获取/设置 Buffer 配置
        RECT rect;
        rect.right = -1; 
        okSetTargetRect(m_hBoard, BUFFER, &rect); 

        // *** 关键：启用硬件内部测试图样 (无相机验证模式) ***
        // 36=VIDEO_IMAGESOURCE, 5=动态垂直条纹
        okSetVideoParam(m_hBoard, 36, 5);

        m_bIsSoftwareMock = false;
    } 
    else {
        // --- 场景 B: 未检测到卡 (Software Mock) ---
        std::cout << "[OKCamera] 未找到采集卡。启用纯软件模拟模式..." << std::endl;
        m_bIsSoftwareMock = true;
        
        // 模拟标准 PAL 分辨率
        m_lWidth = 768;
        m_lHeight = 576;
    }

    InitBufferSize();
    return true;
}

void OKCamera::Close()
{
    StopCapture();
    
    if (m_pWorkBuffer) {
        delete[] m_pWorkBuffer;
        m_pWorkBuffer = nullptr;
    }

    if (m_hBoard) {
        okCloseBoard(m_hBoard);
        m_hBoard = NULL;
    }
}

void OKCamera::InitBufferSize()
{
    // 如果是硬件模式，从驱动获取实际大小
    if (!m_bIsSoftwareMock && m_hBoard) {
        RECT rect;
        rect.right = -1; 
        okSetTargetRect(m_hBoard, BUFFER, &rect); 
        m_lWidth = rect.right - rect.left;
        m_lHeight = rect.bottom - rect.top;
        
        // 防止获取失败
        if (m_lWidth <= 0) m_lWidth = 768;
        if (m_lHeight <= 0) m_lHeight = 576;
    }

    // 分配 SDK 工作内存 (RGB 24位)
    if (m_pWorkBuffer) delete[] m_pWorkBuffer;
    m_pWorkBuffer = new unsigned char[m_lWidth * m_lHeight * 3];
}

bool OKCamera::StartCapture()
{
    if (m_bIsCapturing) return true;
    if (!m_pWorkBuffer) InitBufferSize();

    // 开始前清空队列，防止残留旧数据
    m_pFrameQueue->Clear();

    if (!m_bIsSoftwareMock) {
        // --- 硬件模式：注册回调 ---
        typedef BOOL (CALLBACK *OK_SEQ_PROC)(HANDLE, MLONG);
        if (!okSetSeqCallback(m_hBoard, NULL, (OK_SEQ_PROC)SeqProc, NULL)) return false;
        // 启动无限循环采集 (-1)
        if (okCaptureTo(m_hBoard, BUFFER, 0, -1) <= 0) return false;
    } else {
        std::cout << "[OKCamera] 软件模拟采集开始..." << std::endl;
    }

    m_bIsCapturing = true;
    return true;
}

void OKCamera::StopCapture()
{
    if (m_bIsCapturing) {
        if (!m_bIsSoftwareMock && m_hBoard) {
            okStopCapture(m_hBoard);
            okSetSeqCallback(m_hBoard, NULL, NULL, NULL);
        }
        m_bIsCapturing = false;
    }
}

// [生产者] SDK 回调函数
BOOL CALLBACK OKCamera::SeqProc(HANDLE hBoard, long no)
{
    // 检查指针有效性
    if (!g_pCameraInstance || !g_pCameraInstance->m_pWorkBuffer) return 0;

    // 1. 设置转换目标：指向 m_pWorkBuffer
    BLOCKINFO blk;
    memset(&blk, 0, sizeof(BLOCKINFO));
    blk.iType = BLKHEADER;
    blk.lpBits = g_pCameraInstance->m_pWorkBuffer; // 写入临时工作区
    blk.iBitCount = 24; // RGB
    blk.iWidth = (short)g_pCameraInstance->m_lWidth;
    blk.iHeight = -(short)g_pCameraInstance->m_lHeight; // 负号倒置

    // 2. 转换并拷贝数据 (SDK -> WorkBuffer)
    // 此时数据在 WorkBuffer 中，还没有进队列
    okConvertRect(hBoard, (TARGET)&blk, 0, BUFFER, (short)no, 1);

    // 3. 封装成 vector 并推入队列 (WorkBuffer -> Queue)
    // 这里会发生一次内存拷贝，确保队列里的数据是独立的
    size_t dataSize = g_pCameraInstance->m_lWidth * g_pCameraInstance->m_lHeight * 3;
    std::vector<unsigned char> frameVec(
        g_pCameraInstance->m_pWorkBuffer, 
        g_pCameraInstance->m_pWorkBuffer + dataSize
    );

    // 推入队列 (线程安全)
    g_pCameraInstance->m_pFrameQueue->Push(frameVec);

    return 1;
}

// 辅助：生成纯软件模拟帧
void OKCamera::GenerateSoftwareMockFrame()
{
    if (!m_pWorkBuffer) return;
    m_nSimFrameIndex++;

    int totalBytes = m_lWidth * m_lHeight * 3;
    
    // 生成一个变色的背景
    unsigned char val = m_nSimFrameIndex % 255;
    memset(m_pWorkBuffer, val, totalBytes);

    // 在中间画一个固定颜色的块
    for(int i=0; i<100; i++) {
        for(int j=0; j<100; j++) {
            int idx = ((100+i)*m_lWidth + (100+j)) * 3;
            if(idx < totalBytes) {
                m_pWorkBuffer[idx] = 255; // R
                m_pWorkBuffer[idx+1] = 0; // G
                m_pWorkBuffer[idx+2] = 0; // B
            }
        }
    }

    // 模拟推入队列
    std::vector<unsigned char> frameVec(m_pWorkBuffer, m_pWorkBuffer + totalBytes);
    m_pFrameQueue->Push(frameVec);
    Sleep(33); // 模拟 30fps
}

// [消费者] Python 接口
py::array_t<unsigned char> OKCamera::GetImageForPython()
{
    // 如果是纯软件模拟，在这里手动生产一帧数据
    if (m_bIsSoftwareMock && m_bIsCapturing) {
        GenerateSoftwareMockFrame();
    }

    std::vector<unsigned char> frameData;
    
    // 从队列尝试取出一帧
    if (!m_pFrameQueue || !m_pFrameQueue->Pop(frameData)) {
        // 队列为空，返回空数组
        return py::array_t<unsigned char>();
    }

    // Shape: { H, W, C }
    std::vector<ssize_t> shape = { m_lHeight, m_lWidth, 3 };
    
    // Strides: { W*3, 3, 1 } (单位是字节)
    std::vector<ssize_t> strides = { m_lWidth * 3, 3, 1 };

    // 使用指针构造，pybind11 会拷贝数据
    return py::array_t<unsigned char>(
        shape,      // Shape
        strides,    // Strides
        frameData.data() // Data Pointer
    );
}

// 参数调节
void OKCamera::SetExposureTime(long us) {
    if (!m_bIsSoftwareMock && m_hBoard) okSetCaptureParam(m_hBoard, 20, us);
}

void OKCamera::SetFrameRate(long fps) {
    if (!m_bIsSoftwareMock && m_hBoard) okSetCaptureParam(m_hBoard, 22, fps);
}

// Pybind11 模块定义
PYBIND11_MODULE(ok_camera, m) {
    py::class_<OKCamera>(m, "Camera")
        .def(py::init<>())
        .def("open", &OKCamera::Open)
        .def("close", &OKCamera::Close)
        .def("start", &OKCamera::StartCapture)
        .def("stop", &OKCamera::StopCapture)
        .def("set_exposure", &OKCamera::SetExposureTime)
        .def("set_fps", &OKCamera::SetFrameRate)
        .def("get_image", &OKCamera::GetImageForPython);
}