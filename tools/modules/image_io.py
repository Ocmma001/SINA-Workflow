"""Image coordinates always refer to original pixels, including Unicode paths."""
from pathlib import Path

def read_image(path):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('image could not be decoded')
    return image


def write_image(path, image):
    """Encode with OpenCV, write with Python so Windows preserves Unicode paths."""
    import cv2
    path = Path(path)
    ok, encoded = cv2.imencode(path.suffix, image)
    if not ok:
        raise ValueError('image could not be encoded')
    path.write_bytes(encoded.tobytes())
    return True
