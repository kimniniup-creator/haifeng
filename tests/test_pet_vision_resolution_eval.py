from pathlib import Path
import sys
import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
from run_pet_vision_resolution_eval import paired_frames


def test_rejects_native_inputs_that_would_need_upscaling():
    for shape in ((480,972,3),(540,959,3),(539,960,3)):
        with pytest.raises(ValueError):
            paired_frames(np.zeros(shape,dtype=np.uint8))


def test_same_centered_content_preserves_geometry():
    frame = np.zeros((720,1000,3),dtype=np.uint8)
    frame[81:639,4:996] = 127
    pair,crop = paired_frames(frame)
    assert crop == dict(x=4,y=81,width=992,height=558)
    assert pair[640].shape == (360,640,3)
    assert pair[960].shape == (540,960,3)
    assert np.all(pair[640]==127) and np.all(pair[960]==127)
