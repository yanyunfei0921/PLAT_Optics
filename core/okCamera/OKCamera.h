#pragma once

#define NOMINMAX
#include <windows.h>
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include "SafeFrameQueue.h"

namespace py = pybind11;

// 引入 DLLENTRY 或 SDK 头文件
#ifdef _WIN64
#include "okapi64.h"
#else
#include "okapi32.h"
#endif

class OKCamera
{
public:
    OKCamera();
    ~OKCamera();

    // --- 核心控制 ---
    bool Open();
    void Close();
    bool StartCapture();
    void StopCapture();

    // --- 参数调节 ---
    void SetExposureTime(long us);
    void SetFrameRate(long fps);

    // --- Python 接口 ---
    // 返回 Numpy 数组，线程安全
    py::array_t<unsigned char> GetImageForPython();

    // --- SDK 回调 ---
    static BOOL CALLBACK SeqProc(HANDLE hBoard, long no);

private:
    HANDLE m_hBoard;             // 板卡句柄
    
    // [SDK专用] 临时工作缓冲区，用于接收底层数据
    unsigned char* m_pWorkBuffer; 
    
    // [Python专用] 线程安全队列，用于存放处理好的成品帧
    SafeFrameQueue* m_pFrameQueue;

    long m_lWidth;
    long m_lHeight;
    bool m_bIsCapturing;
    
    // 模拟状态标志
    bool m_bIsSoftwareMock; 
    int  m_nSimFrameIndex;

    void InitBufferSize();
    void GenerateSoftwareMockFrame(); // 纯软件模拟生成函数
};