"""
sdiService.py

SDI Video Capture Service for PLAT_Optics
Wraps the HWS SDK video_capture module for SDI input capture

SDI cameras have different parameters than MvCamera:
- Brightness (0-255)
- Contrast (0-255)
- Saturation (0-255)
- Hue (-128 to 127)

The SDI SDK files are located in core/sdi/:
- hwsys_api.py: Low-level DLL wrapper
- video_capture.py: High-level VideoCapture class
- hwsys.dll: Native SDK library
"""

import sys
import os
import threading
import time
import base64
from collections import deque
from typing import Optional, Callable, Dict, Any

import cv2
import numpy as np

# Import from local SDI module
try:
    from core.sdi import VideoCapture, VideoFrame
    SDI_AVAILABLE = True
except ImportError as e:
    print(f"[SDI Service] Warning: Could not import SDI SDK: {e}")
    SDI_AVAILABLE = False
    VideoCapture = None
    VideoFrame = None


class SDICameraService:
    """
    SDI Camera Service for capturing video from SDI input devices.

    This service wraps the HWS SDK VideoCapture class and provides
    an interface similar to CameraService for consistency.
    """

    def __init__(self, camera_id: int = 3):
        """
        Initialize SDI camera service.

        Args:
            camera_id: Camera ID for this service (default 3)
        """
        self.camera_id = camera_id
        self.running = False
        self.capture: Optional[VideoCapture] = None
        self.channel = 0  # SDI channel (0-based)

        # Frame queue for streaming
        self.frame_queue: deque = deque(maxlen=2)
        self.frame_num = 0
        self._lock = threading.Lock()

        # Image processing settings
        self.threshold = 128
        self.return_binary_image = False

        # SDI-specific parameters (different from MvCamera)
        self.brightness = 136
        self.contrast = 146
        self.saturation = 136
        self.hue = 0

        # Current frame info
        self.current_width = 0
        self.current_height = 0
        self.current_fps = 0.0

        # Callback for frame data
        self._frame_callback: Optional[Callable] = None

        # Initialization flag
        self._initialized = False

    def is_available(self) -> bool:
        """Check if SDI SDK is available."""
        return SDI_AVAILABLE

    def initialize(self, max_width: int = 1920, max_height: int = 1200) -> tuple:
        """
        Initialize the SDI capture system.

        Args:
            max_width: Maximum video width
            max_height: Maximum video height

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not SDI_AVAILABLE:
            return False, "SDI SDK not available"

        if self._initialized:
            return True, "Already initialized"

        try:
            self.capture = VideoCapture()
            success = self.capture.initialize(max_width, max_height)
            if success:
                self._initialized = True
                return True, "SDI system initialized"
            else:
                return False, "Failed to initialize SDI hardware"
        except Exception as e:
            return False, f"SDI initialization error: {str(e)}"

    def get_devices(self) -> list:
        """Get list of available SDI video devices."""
        if not self._initialized or not self.capture:
            return []

        try:
            devices = self.capture.get_video_devices()
            return [
                {
                    'index': d.index,
                    'name': d.name,
                    'resolutions': [
                        {'width': r.width, 'height': r.height, 'fps': r.fps}
                        for r in d.resolutions
                    ]
                }
                for d in devices
            ]
        except Exception as e:
            print(f"[SDI Service] Error getting devices: {e}")
            return []

    def connect(self, channel: int = 0, resolution_index: int = 0) -> tuple:
        """
        Connect to SDI channel and start capture.

        Args:
            channel: SDI channel number (0-based)
            resolution_index: Resolution index (0 = highest)

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self._initialized:
            success, msg = self.initialize()
            if not success:
                return False, msg

        if self.running:
            self.disconnect()

        try:
            self.channel = channel

            # Open channel
            if not self.capture.open_channel(channel, resolution_index=resolution_index):
                return False, f"Failed to open SDI channel {channel}"

            # Set frame callback
            self.capture.set_frame_callback(self._on_frame)

            # Start preview (headless mode)
            self.capture.start_preview(channel)

            self.running = True
            self.frame_num = 0

            return True, f"SDI channel {channel} connected"

        except Exception as e:
            return False, f"SDI connection error: {str(e)}"

    def disconnect(self) -> tuple:
        """
        Disconnect from SDI channel.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.running:
            return True, "Already disconnected"

        try:
            if self.capture:
                self.capture.stop_channel(self.channel)

            self.running = False
            self.frame_queue.clear()

            return True, "SDI disconnected"

        except Exception as e:
            return False, f"SDI disconnect error: {str(e)}"

    def close(self):
        """Close and cleanup SDI resources."""
        self.disconnect()

        if self.capture:
            try:
                self.capture.close()
            except Exception as e:
                print(f"[SDI Service] Error closing capture: {e}")
            self.capture = None

        self._initialized = False

    def _on_frame(self, frame: 'VideoFrame'):
        """
        Internal frame callback from SDI SDK.

        Args:
            frame: VideoFrame object from SDK
        """
        if not self.running:
            return

        try:
            self.frame_num += 1
            self.current_width = frame.width
            self.current_height = frame.height

            # frame.data is already RGB numpy array (H, W, 3)
            rgb_image = frame.data

            # Convert to grayscale for centroid calculation
            gray_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)

            # Calculate centroid and encode frame
            frame_data = self.centroidExtract(gray_image, rgb_image, self.frame_num)

            # Add to queue
            with self._lock:
                self.frame_queue.append(frame_data)

            # Call external callback if set
            if self._frame_callback:
                self._frame_callback(frame_data)

        except Exception as e:
            print(f"[SDI Service] Frame processing error: {e}")

    def centroidExtract(self, gray_image: np.ndarray, rgb_image: np.ndarray, frame_num: int) -> dict:
        """
        Calculate centroid from grayscale image and encode frame.

        Args:
            gray_image: Grayscale image for centroid calculation
            rgb_image: RGB image for display
            frame_num: Frame number

        Returns:
            Dict with frame data and centroid info
        """
        height, width = gray_image.shape

        # Apply threshold for binary image
        _, binary = cv2.threshold(gray_image, self.threshold, 255, cv2.THRESH_BINARY)

        # Calculate centroid using moments
        M = cv2.moments(binary)
        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        else:
            cx, cy = -1.0, -1.0

        # Choose image to encode
        if self.return_binary_image:
            # Convert binary to BGR for encoding
            encode_image = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        else:
            # Convert RGB to BGR for OpenCV encoding
            encode_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)

        # Encode to JPEG
        _, jpeg_data = cv2.imencode('.jpg', encode_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        base64_image = base64.b64encode(jpeg_data).decode('utf-8')

        return {
            'image': f'data:image/jpeg;base64,{base64_image}',
            'width': width,
            'height': height,
            'centroidX': round(cx, 2) if cx >= 0 else -1,
            'centroidY': round(cy, 2) if cy >= 0 else -1,
            'frameNum': frame_num
        }

    def getFrame(self) -> Optional[dict]:
        """
        Get the latest frame from queue.

        Returns:
            Frame data dict or None if no frame available
        """
        with self._lock:
            if self.frame_queue:
                return self.frame_queue[-1]
        return None

    def set_frame_callback(self, callback: Optional[Callable]):
        """Set external frame callback."""
        self._frame_callback = callback

    # ========================================================================
    # SDI-Specific Parameter Methods
    # ========================================================================

    def setThreshold(self, value: int) -> bool:
        """Set binary threshold value."""
        self.threshold = max(0, min(255, value))
        return True

    def getThreshold(self) -> int:
        """Get binary threshold value."""
        return self.threshold

    def setBrightness(self, value: int) -> bool:
        """
        Set brightness (0-255).

        Args:
            value: Brightness value

        Returns:
            True if successful
        """
        self.brightness = max(0, min(255, value))
        return self._apply_video_params()

    def getBrightness(self) -> int:
        """Get brightness value."""
        return self.brightness

    def setContrast(self, value: int) -> bool:
        """
        Set contrast (0-255).

        Args:
            value: Contrast value

        Returns:
            True if successful
        """
        self.contrast = max(0, min(255, value))
        return self._apply_video_params()

    def getContrast(self) -> int:
        """Get contrast value."""
        return self.contrast

    def setSaturation(self, value: int) -> bool:
        """
        Set saturation (0-255).

        Args:
            value: Saturation value

        Returns:
            True if successful
        """
        self.saturation = max(0, min(255, value))
        return self._apply_video_params()

    def getSaturation(self) -> int:
        """Get saturation value."""
        return self.saturation

    def setHue(self, value: int) -> bool:
        """
        Set hue (-128 to 127).

        Args:
            value: Hue value

        Returns:
            True if successful
        """
        self.hue = max(-128, min(127, value))
        return self._apply_video_params()

    def getHue(self) -> int:
        """Get hue value."""
        return self.hue

    def _apply_video_params(self) -> bool:
        """Apply video parameters to SDI hardware."""
        if not self.running or not self.capture:
            return False

        try:
            self.capture.set_video_parameters(
                self.channel,
                brightness=self.brightness,
                contrast=self.contrast,
                saturation=self.saturation,
                hue=self.hue
            )
            return True
        except Exception as e:
            print(f"[SDI Service] Error applying video params: {e}")
            return False

    def setImageMode(self, mode: int) -> bool:
        """
        Set image mode (0=original, 1=binary).

        Args:
            mode: 0 for original, 1 for binary

        Returns:
            True if successful
        """
        self.return_binary_image = (mode == 1)
        return True

    def getAllParams(self) -> dict:
        """
        Get all current parameters.

        Returns:
            Dict with all parameter values
        """
        return {
            'threshold': self.threshold,
            'brightness': self.brightness,
            'contrast': self.contrast,
            'saturation': self.saturation,
            'hue': self.hue,
            'width': self.current_width,
            'height': self.current_height,
            'imageMode': 1 if self.return_binary_image else 0
        }


# Singleton instance
_sdi_service: Optional[SDICameraService] = None


def get_sdi_service(camera_id: int = 3) -> SDICameraService:
    """
    Get or create the SDI service singleton.

    Args:
        camera_id: Camera ID for the service

    Returns:
        SDICameraService instance
    """
    global _sdi_service
    if _sdi_service is None:
        _sdi_service = SDICameraService(camera_id)
    return _sdi_service
