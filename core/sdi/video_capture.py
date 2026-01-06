"""
video_capture.py

High-level object-oriented wrapper for hwsys.dll video capture

This module provides a clean, Pythonic interface for:
- Multi-channel video capture
- Frame retrieval as numpy arrays
- Hardware abstraction and lifecycle management
- Thread-safe callback handling
- Headless operation (no GUI dependencies)
"""

import ctypes
import queue
import threading
import time
from typing import Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

from .hwsys_api import (
    get_dll,
    HwsysDLL,
    RECT,
    RAWSTREAM_DIRECT_CALLBACK,
    VIDEOSTATUS_CALLBACK,
    RAWAUDIO_DIRECT_CALLBACK
)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class VideoResolution:
    """Video resolution configuration"""
    width: int
    height: int
    fps: int

    def __str__(self):
        return f"{self.width}x{self.height}@{self.fps}fps"


@dataclass
class VideoDeviceInfo:
    """Video device information"""
    index: int
    name: str
    resolutions: List[VideoResolution]


@dataclass
class AudioDeviceInfo:
    """Audio device information"""
    index: int
    name: str


@dataclass
class VideoFrame:
    """Video frame data container"""
    channel: int
    width: int
    height: int
    frame_type: int
    data: np.ndarray  # RGB or grayscale numpy array
    timestamp: float


# ============================================================================
# Video Capture System
# ============================================================================

class VideoCapture:
    """
    High-level interface for multi-channel video capture

    Example usage:
        capture = VideoCapture()
        capture.initialize()

        # Get device info
        devices = capture.get_video_devices()
        print(f"Found {len(devices)} video devices")

        # Open channel 0
        capture.open_channel(0, resolution_index=0)

        # Register frame callback
        def on_frame(frame: VideoFrame):
            print(f"Channel {frame.channel}: {frame.width}x{frame.height}")

        capture.set_frame_callback(on_frame)

        # Start preview (headless mode, no window)
        capture.start_preview(0)

        # ... capture for some time ...

        # Cleanup
        capture.stop_channel(0)
        capture.close()
    """

    MAX_CHANNELS = 64
    MAX_AUDIO_BUFSIZE = 1024 * 8 * 2

    def __init__(self, dll_path: Optional[str] = None):
        """
        Initialize video capture system

        Args:
            dll_path: Path to hwsys.dll (auto-detected if None)
        """
        self.dll = get_dll(dll_path)
        self._initialized = False
        self._channels_open: Dict[int, int] = {}  # channel -> handle
        self._audio_channels_open: Dict[int, int] = {}  # channel -> handle

        # Device information cache
        self._video_devices: List[VideoDeviceInfo] = []
        self._audio_devices: List[AudioDeviceInfo] = []
        self._total_video_channels = 0
        self._total_audio_channels = 0

        # Callback management (must be kept alive to prevent GC)
        self._video_callback_func: Optional[RAWSTREAM_DIRECT_CALLBACK] = None
        self._status_callback_func: Optional[VIDEOSTATUS_CALLBACK] = None
        self._audio_callback_func: Optional[RAWAUDIO_DIRECT_CALLBACK] = None

        # User callbacks
        self._frame_callback: Optional[Callable[[VideoFrame], None]] = None
        self._status_callback: Optional[Callable[[int, bool], None]] = None
        self._audio_callback: Optional[Callable[[int, bytes, int], None]] = None

        # Thread safety
        self._lock = threading.Lock()

        # FPS tracking
        self._fps_counter: Dict[int, int] = {}
        self._fps_values: Dict[int, float] = {}

        # Producer-consumer queues (only keep latest frame, drop old ones)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._status_queue: queue.Queue = queue.Queue(maxsize=1)
        self._audio_queue: queue.Queue = queue.Queue(maxsize=1)

        # Consumer threads and shutdown event
        self._shutdown_event = threading.Event()
        self._frame_consumer_thread: Optional[threading.Thread] = None
        self._status_consumer_thread: Optional[threading.Thread] = None
        self._audio_consumer_thread: Optional[threading.Thread] = None

    # ========================================================================
    # System Initialization
    # ========================================================================

    def initialize(self, max_video_width: int = 1920, max_video_height: int = 1200) -> bool:
        """
        Initialize the hardware system

        Args:
            max_video_width: Maximum video width to allocate memory for
            max_video_height: Maximum video height to allocate memory for

        Returns:
            True if successful, False otherwise
        """
        if self._initialized:
            self.close()

        # Set maximum video size for memory allocation
        self.dll.SetMax_VideoSize(max_video_width, max_video_height)

        # Initialize hardware
        ret = self.dll.InitHwDSPs()
        if ret < 0:
            return False

        self._initialized = True

        # Query device information
        self._query_devices()

        return True

    def close(self):
        """Cleanup and release all resources"""
        if not self._initialized:
            return

        # Signal shutdown to consumer threads
        self._shutdown_event.set()

        # Stop all channels
        for channel in list(self._channels_open.keys()):
            self.stop_channel(channel)

        for channel in list(self._audio_channels_open.keys()):
            self.stop_audio_channel(channel)

        # Wait for consumer threads to finish
        self._stop_consumer_threads()

        # Deinitialize hardware
        self.dll.DeInitHwDSPs()
        self._initialized = False

    def _stop_consumer_threads(self, timeout: float = 2.0):
        """Stop all consumer threads gracefully"""
        threads = [
            self._frame_consumer_thread,
            self._status_consumer_thread,
            self._audio_consumer_thread,
        ]
        for thread in threads:
            if thread is not None and thread.is_alive():
                thread.join(timeout=timeout)

        self._frame_consumer_thread = None
        self._status_consumer_thread = None
        self._audio_consumer_thread = None

    def _query_devices(self):
        """Query and cache device information"""
        # Get current system device
        self.dll.GetCurrSystemDevice()

        # Video devices
        self._total_video_channels = self.dll.GetVideoTotalChannels()
        self._video_devices = []

        for i in range(self._total_video_channels):
            # Get device name
            name_buf = (ctypes.c_char * 256)()
            self.dll.GetVideoNameByIndex(i, name_buf)
            name = name_buf.value.decode('ascii', errors='ignore').rstrip('\x00')

            # Get supported resolutions
            resolutions = []
            num_resolutions = self.dll.GetVideoMaxResIndex(i)
            for res_idx in range(num_resolutions):
                width = self.dll.GetVideoMaxResWidthByIndex(i, res_idx)
                height = self.dll.GetVideoMaxResHeightByIndex(i, res_idx)
                fps = self.dll.GetVideoMaxResFpsByIndex(i, res_idx)
                resolutions.append(VideoResolution(width, height, fps))

            self._video_devices.append(VideoDeviceInfo(i, name, resolutions))

        # Audio devices
        self._total_audio_channels = self.dll.GetAudioTotalChannels()
        self._audio_devices = []

        for i in range(self._total_audio_channels):
            name_buf = (ctypes.c_char * 256)()
            self.dll.GetAudioNameByIndex(i, name_buf)
            name = name_buf.value.decode('ascii', errors='ignore').rstrip('\x00')
            self._audio_devices.append(AudioDeviceInfo(i, name))

    # ========================================================================
    # Device Information
    # ========================================================================

    def get_video_devices(self) -> List[VideoDeviceInfo]:
        """Get list of available video devices"""
        if not self._initialized:
            raise RuntimeError("System not initialized. Call initialize() first.")
        return self._video_devices.copy()

    def get_audio_devices(self) -> List[AudioDeviceInfo]:
        """Get list of available audio devices"""
        if not self._initialized:
            raise RuntimeError("System not initialized. Call initialize() first.")
        return self._audio_devices.copy()

    # ========================================================================
    # Video Channel Control
    # ========================================================================

    def open_channel(
        self,
        channel: int,
        video_index: Optional[int] = None,
        resolution_index: int = 0
    ) -> bool:
        """
        Open a video channel

        Args:
            channel: Channel number (0-63)
            video_index: Video device index (defaults to channel number)
            resolution_index: Resolution index (0 = highest resolution)

        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            raise RuntimeError("System not initialized. Call initialize() first.")

        if channel < 0 or channel >= self.MAX_CHANNELS:
            raise ValueError(f"Channel must be 0-{self.MAX_CHANNELS-1}")

        if video_index is None:
            video_index = channel

        if video_index >= len(self._video_devices):
            raise ValueError(f"Video index {video_index} out of range")

        device = self._video_devices[video_index]
        if resolution_index >= len(device.resolutions):
            raise ValueError(f"Resolution index {resolution_index} out of range")

        res = device.resolutions[resolution_index]

        # Close if already open
        if channel in self._channels_open:
            self.stop_channel(channel)

        # Open video channel
        handle = self.dll.VideoChannelOpen(
            channel,
            video_index,
            res.width,
            res.height,
            res.fps
        )

        if handle < 0:
            return False

        self._channels_open[channel] = handle
        self._fps_counter[channel] = 0
        self._fps_values[channel] = 0.0

        return True

    def start_preview(self, channel: int, window_handle: Optional[int] = None):
        """
        Start video preview on a channel

        Args:
            channel: Channel number
            window_handle: Window handle for preview (None for headless)
        """
        if channel not in self._channels_open:
            raise RuntimeError(f"Channel {channel} not open. Call open_channel() first.")

        handle = self._channels_open[channel]

        # Create empty rect for headless operation
        rect = RECT(0, 0, 0, 0)

        # Register callbacks before starting preview
        if self._video_callback_func is None:
            self._register_internal_callbacks()

        # Register callback for this channel
        self.dll.RegisterRAWDirectCallback(channel, self._video_callback_func, None)
        if self._status_callback_func:
            self.dll.RegisterVideoStatusCallback(channel, self._status_callback_func, None)

        # Start preview (pass None for headless)
        wnd_ptr = window_handle if window_handle is not None else None
        self.dll.StartVideoPreview(handle, wnd_ptr, ctypes.byref(rect))

    def stop_channel(self, channel: int):
        """Stop and close a video channel"""
        if channel in self._channels_open:
            handle = self._channels_open[channel]
            self.dll.StopVideoCapture(handle)
            del self._channels_open[channel]

    # ========================================================================
    # Audio Channel Control
    # ========================================================================

    def open_audio_channel(
        self,
        channel: int,
        audio_index: Optional[int] = None,
        buffer_size: int = MAX_AUDIO_BUFSIZE
    ) -> bool:
        """
        Open an audio channel

        Args:
            channel: Channel number
            audio_index: Audio device index (defaults to channel number)
            buffer_size: Audio buffer size

        Returns:
            True if successful
        """
        if not self._initialized:
            raise RuntimeError("System not initialized")

        if audio_index is None:
            audio_index = channel

        if audio_index >= len(self._audio_devices):
            raise ValueError(f"Audio index {audio_index} out of range")

        # Close if already open
        if channel in self._audio_channels_open:
            self.stop_audio_channel(channel)

        # Open audio channel
        handle = self.dll.AudioChannelOpen(channel, audio_index, buffer_size)
        if handle < 0:
            return False

        self._audio_channels_open[channel] = handle

        # Register audio callback
        if self._audio_callback_func is None:
            self._register_internal_callbacks()

        self.dll.RegisterAudioDirectCallback(channel, self._audio_callback_func, None)

        return True

    def start_audio_playback(self, channel: int):
        """Start audio playback on a channel"""
        if channel not in self._audio_channels_open:
            raise RuntimeError(f"Audio channel {channel} not open")

        handle = self._audio_channels_open[channel]
        self.dll.AudioOutOpen(channel, None)
        self.dll.AudioOutPlay(channel)

    def pause_audio_playback(self, channel: int):
        """Pause audio playback on a channel"""
        if channel in self._audio_channels_open:
            self.dll.AudioOutPause(channel)

    def stop_audio_channel(self, channel: int):
        """Stop and close an audio channel"""
        if channel in self._audio_channels_open:
            handle = self._audio_channels_open[channel]
            self.dll.StopAudioCapture(handle)
            del self._audio_channels_open[channel]

    # ========================================================================
    # Video Control
    # ========================================================================

    def set_video_parameters(
        self,
        channel: int,
        brightness: int = 136,
        contrast: int = 146,
        saturation: int = 136,
        hue: int = 0
    ):
        """
        Set video color parameters

        Args:
            channel: Channel number
            brightness: Brightness (0-255)
            contrast: Contrast (0-255)
            saturation: Saturation (0-255)
            hue: Hue (-128 to 127)
        """
        if channel not in self._channels_open:
            raise RuntimeError(f"Channel {channel} not open")

        self.dll.SetVideoPara(channel, brightness, contrast, saturation, hue)

    def save_snapshot(self, channel: int, filepath: str) -> bool:
        """
        Save current frame as BMP image

        Args:
            channel: Channel number
            filepath: Output file path (BMP format)

        Returns:
            True if successful
        """
        if channel not in self._channels_open:
            raise RuntimeError(f"Channel {channel} not open")

        ret = self.dll.SaveCaptureImage(channel, filepath.encode('ascii'))
        return ret >= 0

    # ========================================================================
    # Callback Management
    # ========================================================================

    def set_frame_callback(self, callback: Optional[Callable[[VideoFrame], None]]):
        """
        Set callback for receiving video frames

        Args:
            callback: Function(VideoFrame) -> None
        """
        self._frame_callback = callback
        if callback is not None:
            self._start_frame_consumer()

    def set_status_callback(self, callback: Optional[Callable[[int, bool], None]]):
        """
        Set callback for video status changes

        Args:
            callback: Function(channel: int, signal_present: bool) -> None
        """
        self._status_callback = callback
        if callback is not None:
            self._start_status_consumer()

    def set_audio_callback(self, callback: Optional[Callable[[int, bytes, int], None]]):
        """
        Set callback for audio data

        Args:
            callback: Function(channel: int, data: bytes, frame_type: int) -> None
        """
        self._audio_callback = callback
        if callback is not None:
            self._start_audio_consumer()

    def _start_frame_consumer(self):
        """Start frame consumer thread if not already running"""
        if self._frame_consumer_thread is None or not self._frame_consumer_thread.is_alive():
            self._frame_consumer_thread = threading.Thread(
                target=self._frame_consumer_loop,
                daemon=True,
                name="FrameConsumer"
            )
            self._frame_consumer_thread.start()

    def _start_status_consumer(self):
        """Start status consumer thread if not already running"""
        if self._status_consumer_thread is None or not self._status_consumer_thread.is_alive():
            self._status_consumer_thread = threading.Thread(
                target=self._status_consumer_loop,
                daemon=True,
                name="StatusConsumer"
            )
            self._status_consumer_thread.start()

    def _start_audio_consumer(self):
        """Start audio consumer thread if not already running"""
        if self._audio_consumer_thread is None or not self._audio_consumer_thread.is_alive():
            self._audio_consumer_thread = threading.Thread(
                target=self._audio_consumer_loop,
                daemon=True,
                name="AudioConsumer"
            )
            self._audio_consumer_thread.start()

    def _frame_consumer_loop(self):
        """Consumer loop for frame queue"""
        while not self._shutdown_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.1)
                if self._frame_callback:
                    self._frame_callback(frame)
            except queue.Empty:
                continue

    def _status_consumer_loop(self):
        """Consumer loop for status queue"""
        while not self._shutdown_event.is_set():
            try:
                channel, signal_present = self._status_queue.get(timeout=0.1)
                if self._status_callback:
                    self._status_callback(channel, signal_present)
            except queue.Empty:
                continue

    def _audio_consumer_loop(self):
        """Consumer loop for audio queue"""
        while not self._shutdown_event.is_set():
            try:
                channel, audio_bytes, frame_type = self._audio_queue.get(timeout=0.1)
                if self._audio_callback:
                    self._audio_callback(channel, audio_bytes, frame_type)
            except queue.Empty:
                continue

    def _register_internal_callbacks(self):
        """Register internal callback functions (must be kept alive)"""
        self._video_callback_func = RAWSTREAM_DIRECT_CALLBACK(self._on_video_frame)
        self._status_callback_func = VIDEOSTATUS_CALLBACK(self._on_video_status)
        self._audio_callback_func = RAWAUDIO_DIRECT_CALLBACK(self._on_audio_data)

    def _on_video_frame(
        self,
        channel: int,
        data_buf: ctypes.c_void_p,
        frame_type: int,
        width: int,
        height: int,
        context: ctypes.c_void_p
    ):
        """Internal video frame callback (called from native thread)"""
        # Update FPS counter
        self._fps_counter[channel] = self._fps_counter.get(channel, 0) + 1

        # Only process if callback is registered
        if self._frame_callback:
            # Convert YUV to RGB
            rgb_size = width * height * 3

            # Allocate RGB buffer
            rgb_buf = (ctypes.c_char * rgb_size)()
            rgb_ptr = ctypes.cast(rgb_buf, ctypes.c_void_p)

            # Convert YUV to RGB
            self.dll.ChangeYUVToRGB(data_buf, rgb_ptr, width, height)

            # Create numpy array from RGB data
            rgb_array = np.frombuffer(rgb_buf, dtype=np.uint8)
            rgb_array = rgb_array.reshape((height, width, 3))

            # Create frame object
            frame = VideoFrame(
                channel=channel,
                width=width,
                height=height,
                frame_type=frame_type,
                data=rgb_array.copy(),  # Copy to prevent buffer issues
                timestamp=time.time()
            )

            # Put frame in queue, dropping old frame if queue is full
            try:
                # Try to remove old frame first (non-blocking)
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                # Put new frame
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                pass  # Drop frame if still full (shouldn't happen)

    def _on_video_status(self, channel: int, status: int, context: ctypes.c_void_p):
        """Internal video status callback"""
        if self._status_callback:
            signal_present = (status != 0)
            # Put status in queue, dropping old if full
            try:
                try:
                    self._status_queue.get_nowait()
                except queue.Empty:
                    pass
                self._status_queue.put_nowait((channel, signal_present))
            except queue.Full:
                pass

    def _on_audio_data(
        self,
        channel: int,
        data_buf: ctypes.c_void_p,
        frame_type: int,
        size: int,
        context: ctypes.c_void_p
    ):
        """Internal audio data callback"""
        if self._audio_callback:
            # Copy audio data to bytes
            audio_bytes = ctypes.string_at(data_buf, size)

            # Put audio in queue, dropping old if full
            try:
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    pass
                self._audio_queue.put_nowait((channel, audio_bytes, frame_type))
            except queue.Full:
                pass

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def get_fps(self, channel: int) -> float:
        """Get current FPS for a channel"""
        return self._fps_values.get(channel, 0.0)

    def reset_fps_counter(self, channel: int):
        """Reset FPS counter for a channel"""
        count = self._fps_counter.get(channel, 0)
        self._fps_values[channel] = float(count)
        self._fps_counter[channel] = 0

    def is_channel_open(self, channel: int) -> bool:
        """Check if a channel is open"""
        return channel in self._channels_open

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False
