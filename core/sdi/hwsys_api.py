"""
hwsys_api.py

Low-level ctypes wrapper for hwsys.dll
Direct mapping of C# P/Invoke declarations to Python ctypes

This module provides the raw DLL interface without abstraction.
For higher-level usage, see video_capture.py
"""

import ctypes
from ctypes import c_int, c_void_p, POINTER, Structure, CFUNCTYPE
import sys
import os
from typing import Callable, Optional


# ============================================================================
# Structure Definitions
# ============================================================================

class RECT(Structure):
    """Rectangle structure for video preview regions"""
    _fields_ = [
        ("left", c_int),
        ("top", c_int),
        ("right", c_int),
        ("bottom", c_int)
    ]


# ============================================================================
# Callback Function Types (Cdecl calling convention)
# ============================================================================

# Raw video stream callback
# void callback(int channelNumber, void* DataBuf, int FrameType, int width, int height, void* context)
RAWSTREAM_DIRECT_CALLBACK = CFUNCTYPE(
    None,  # return type
    c_int,  # channelNumber
    c_void_p,  # DataBuf
    c_int,  # FrameType
    c_int,  # width
    c_int,  # height
    c_void_p  # context
)

# Video status callback (signal in/out detection)
# void callback(int channelNumber, int status, void* context)
VIDEOSTATUS_CALLBACK = CFUNCTYPE(
    None,  # return type
    c_int,  # channelNumber
    c_int,  # status (0=lost, 1=in)
    c_void_p  # context
)

# Raw audio stream callback
# void callback(int channelNumber, void* DataBuf, int FrameType, int size, void* context)
RAWAUDIO_DIRECT_CALLBACK = CFUNCTYPE(
    None,  # return type
    c_int,  # channelNumber
    c_void_p,  # DataBuf
    c_int,  # FrameType
    c_int,  # size
    c_void_p  # context
)


# ============================================================================
# DLL Loader
# ============================================================================

class HwsysDLL:
    """Wrapper class for hwsys.dll with proper function signatures"""

    def __init__(self, dll_path: Optional[str] = None):
        """
        Load hwsys.dll and configure function prototypes

        Args:
            dll_path: Full path to hwsys.dll. If None, searches in:
                      - Package directory (core/sdi/)
                      - Current directory
        """
        if dll_path is None:
            dll_path = self._find_dll()

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"hwsys.dll not found at: {dll_path}")

        self.dll = ctypes.CDLL(dll_path)
        self._setup_functions()

    def _find_dll(self) -> str:
        """Search for hwsys.dll in common locations"""
        # Get the directory where this module is located
        module_dir = os.path.dirname(os.path.abspath(__file__))

        search_paths = [
            os.path.join(module_dir, "hwsys.dll"),  # Package directory
            "hwsys.dll",  # Current directory
            os.path.join("..", "..", "bin64", "hwsys.dll"),  # x64
        ]

        for path in search_paths:
            if os.path.exists(path):
                return os.path.abspath(path)

        # Default to package directory
        return os.path.join(module_dir, "hwsys.dll")

    def _setup_functions(self):
        """Configure argument and return types for all DLL functions"""

        # ====================================================================
        # System Initialization
        # ====================================================================

        # int InitHwDSPs()
        self.InitHwDSPs = self.dll.InitHwDSPs
        self.InitHwDSPs.argtypes = []
        self.InitHwDSPs.restype = c_int

        # int DeInitHwDSPs()
        self.DeInitHwDSPs = self.dll.DeInitHwDSPs
        self.DeInitHwDSPs.argtypes = []
        self.DeInitHwDSPs.restype = c_int

        # void SetMax_VideoSize(int width, int height)
        self.SetMax_VideoSize = self.dll.SetMax_VideoSize
        self.SetMax_VideoSize.argtypes = [c_int, c_int]
        self.SetMax_VideoSize.restype = None

        # ====================================================================
        # Device Information
        # ====================================================================

        # int GetCurrSystemDevice()
        self.GetCurrSystemDevice = self.dll.GetCurrSystemDevice
        self.GetCurrSystemDevice.argtypes = []
        self.GetCurrSystemDevice.restype = c_int

        # int GetVideoTotalChannels()
        self.GetVideoTotalChannels = self.dll.GetVideoTotalChannels
        self.GetVideoTotalChannels.argtypes = []
        self.GetVideoTotalChannels.restype = c_int

        # int GetAudioTotalChannels()
        self.GetAudioTotalChannels = self.dll.GetAudioTotalChannels
        self.GetAudioTotalChannels.argtypes = []
        self.GetAudioTotalChannels.restype = c_int

        # int GetVideoNameByIndex(int videoIndex, char* strname)
        self.GetVideoNameByIndex = self.dll.GetVideoNameByIndex
        self.GetVideoNameByIndex.argtypes = [c_int, POINTER(ctypes.c_char)]
        self.GetVideoNameByIndex.restype = c_int

        # int GetAudioNameByIndex(int audioIndex, char* strname)
        self.GetAudioNameByIndex = self.dll.GetAudioNameByIndex
        self.GetAudioNameByIndex.argtypes = [c_int, POINTER(ctypes.c_char)]
        self.GetAudioNameByIndex.restype = c_int

        # ====================================================================
        # Video Channel Management
        # ====================================================================

        # int VideoChannelOpen(int nChannel, int videoIndex, int w, int h, int fps)
        self.VideoChannelOpen = self.dll.VideoChannelOpen
        self.VideoChannelOpen.argtypes = [c_int, c_int, c_int, c_int, c_int]
        self.VideoChannelOpen.restype = c_int

        # int StopVideoCapture(int nChannel)
        self.StopVideoCapture = self.dll.StopVideoCapture
        self.StopVideoCapture.argtypes = [c_int]
        self.StopVideoCapture.restype = c_int

        # int StartVideoPreview(int hChannel, void* WndHandle, RECT* rect)
        self.StartVideoPreview = self.dll.StartVideoPreview
        self.StartVideoPreview.argtypes = [c_int, c_void_p, POINTER(RECT)]
        self.StartVideoPreview.restype = c_int

        # ====================================================================
        # Video Resolution Information
        # ====================================================================

        # int GetVideoMaxResIndex(int nChannel)
        self.GetVideoMaxResIndex = self.dll.GetVideoMaxResIndex
        self.GetVideoMaxResIndex.argtypes = [c_int]
        self.GetVideoMaxResIndex.restype = c_int

        # int GetVideoMaxResWidthByIndex(int videoIndex, int ResIndex)
        self.GetVideoMaxResWidthByIndex = self.dll.GetVideoMaxResWidthByIndex
        self.GetVideoMaxResWidthByIndex.argtypes = [c_int, c_int]
        self.GetVideoMaxResWidthByIndex.restype = c_int

        # int GetVideoMaxResHeightByIndex(int videoIndex, int ResIndex)
        self.GetVideoMaxResHeightByIndex = self.dll.GetVideoMaxResHeightByIndex
        self.GetVideoMaxResHeightByIndex.argtypes = [c_int, c_int]
        self.GetVideoMaxResHeightByIndex.restype = c_int

        # int GetVideoMaxResFpsByIndex(int videoIndex, int ResIndex)
        self.GetVideoMaxResFpsByIndex = self.dll.GetVideoMaxResFpsByIndex
        self.GetVideoMaxResFpsByIndex.argtypes = [c_int, c_int]
        self.GetVideoMaxResFpsByIndex.restype = c_int

        # ====================================================================
        # Video Control and Parameters
        # ====================================================================

        # int SetVideoPara(int hChannel, int Brightness, int Contrast, int Saturation, int Hue)
        self.SetVideoPara = self.dll.SetVideoPara
        self.SetVideoPara.argtypes = [c_int, c_int, c_int, c_int, c_int]
        self.SetVideoPara.restype = c_int

        # int OpenVideoColorSetting(int nChannel)
        self.OpenVideoColorSetting = self.dll.OpenVideoColorSetting
        self.OpenVideoColorSetting.argtypes = [c_int]
        self.OpenVideoColorSetting.restype = c_int

        # ====================================================================
        # Callback Registration
        # ====================================================================

        # int RegisterRAWDirectCallback(int nChannel, RAWSTREAM_DIRECT_CALLBACK callback, void* context)
        self.RegisterRAWDirectCallback = self.dll.RegisterRAWDirectCallback
        self.RegisterRAWDirectCallback.argtypes = [c_int, RAWSTREAM_DIRECT_CALLBACK, c_void_p]
        self.RegisterRAWDirectCallback.restype = c_int

        # int RegisterVideoStatusCallback(int nChannel, VIDEOSTATUS_CALLBACK callback, void* context)
        self.RegisterVideoStatusCallback = self.dll.RegisterVideoStatusCallback
        self.RegisterVideoStatusCallback.argtypes = [c_int, VIDEOSTATUS_CALLBACK, c_void_p]
        self.RegisterVideoStatusCallback.restype = c_int

        # int RegisterAudioDirectCallback(int nChannel, RAWAUDIO_DIRECT_CALLBACK callback, void* context)
        self.RegisterAudioDirectCallback = self.dll.RegisterAudioDirectCallback
        self.RegisterAudioDirectCallback.argtypes = [c_int, RAWAUDIO_DIRECT_CALLBACK, c_void_p]
        self.RegisterAudioDirectCallback.restype = c_int

        # ====================================================================
        # Image Processing
        # ====================================================================

        # void ChangeYUVToRGB(void* yuvdata, void* rgbdata, int width, int height)
        self.ChangeYUVToRGB = self.dll.ChangeYUVToRGB
        self.ChangeYUVToRGB.argtypes = [c_void_p, c_void_p, c_int, c_int]
        self.ChangeYUVToRGB.restype = None

        # void ChangeYUVToGrayRGB(void* yuvdata, void* rgbdata, int width, int height)
        self.ChangeYUVToGrayRGB = self.dll.ChangeYUVToGrayRGB
        self.ChangeYUVToGrayRGB.argtypes = [c_void_p, c_void_p, c_int, c_int]
        self.ChangeYUVToGrayRGB.restype = None

        # int SaveCaptureImage(int hChannel, char* path)
        self.SaveCaptureImage = self.dll.SaveCaptureImage
        self.SaveCaptureImage.argtypes = [c_int, ctypes.c_char_p]
        self.SaveCaptureImage.restype = c_int

        # ====================================================================
        # Audio Channel Management
        # ====================================================================

        # int AudioChannelOpen(int nChannel, int audioIndex, int buffsize)
        self.AudioChannelOpen = self.dll.AudioChannelOpen
        self.AudioChannelOpen.argtypes = [c_int, c_int, c_int]
        self.AudioChannelOpen.restype = c_int

        # int StopAudioCapture(int nChannel)
        self.StopAudioCapture = self.dll.StopAudioCapture
        self.StopAudioCapture.argtypes = [c_int]
        self.StopAudioCapture.restype = c_int

        # int AudioOutOpen(int nChannel, void* WndHandle)
        self.AudioOutOpen = self.dll.AudioOutOpen
        self.AudioOutOpen.argtypes = [c_int, c_void_p]
        self.AudioOutOpen.restype = c_int

        # int AudioOutPause(int nChannel)
        self.AudioOutPause = self.dll.AudioOutPause
        self.AudioOutPause.argtypes = [c_int]
        self.AudioOutPause.restype = c_int

        # int AudioOutPlay(int nChannel)
        self.AudioOutPlay = self.dll.AudioOutPlay
        self.AudioOutPlay.argtypes = [c_int]
        self.AudioOutPlay.restype = c_int


# ============================================================================
# Global instance (singleton pattern)
# ============================================================================

_dll_instance: Optional[HwsysDLL] = None


def get_dll(dll_path: Optional[str] = None) -> HwsysDLL:
    """
    Get or create the global DLL instance

    Args:
        dll_path: Path to hwsys.dll (only used on first call)

    Returns:
        HwsysDLL instance
    """
    global _dll_instance
    if _dll_instance is None:
        _dll_instance = HwsysDLL(dll_path)
    return _dll_instance
