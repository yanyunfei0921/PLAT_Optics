import os
import sys
sys.path.append(os.getenv('MVCAM_COMMON_RUNENV') + "/Sample/python/MvImport")
from MvCameraControl_class import *  # type: ignore

class CameraService:
    def __init__(self):
        pass

    def initCamera(self):
        MvCamera.MV_CC_Initialize()
        