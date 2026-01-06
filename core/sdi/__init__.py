"""
SDI Video Capture SDK wrapper for PLAT_Optics

This package contains:
- hwsys_api.py: Low-level ctypes wrapper for hwsys.dll
- video_capture.py: High-level VideoCapture class
- hwsys.dll: Native SDK library (must be present in this directory)
"""

from .video_capture import VideoCapture, VideoFrame, VideoResolution, VideoDeviceInfo
from .hwsys_api import get_dll, HwsysDLL, RECT

__all__ = [
    'VideoCapture',
    'VideoFrame',
    'VideoResolution',
    'VideoDeviceInfo',
    'get_dll',
    'HwsysDLL',
    'RECT'
]
