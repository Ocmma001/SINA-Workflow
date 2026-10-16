"""Image coordinates always refer to original pixels, including Unicode paths."""
from pathlib import Path

def read_image(path):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('image could not be decoded')
    return image
