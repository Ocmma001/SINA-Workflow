"""Bounded OCR preprocessing and original-pixel coordinates; no cloud calls."""
from functools import lru_cache
import math
from pathlib import Path


@lru_cache(maxsize=2)
def _reader(model_dir, user_dir, device, model_signature):
    import easyocr
    gpu = False if device == 'cpu' else device if device.startswith('cuda:') else 'cuda:'+device
    return easyocr.Reader(['en'], gpu=gpu, model_storage_directory=model_dir,
                          user_network_directory=user_dir, download_enabled=False)


def clear_reader_cache():
    _reader.cache_clear()


def _prepare_image(image, min_side, preprocess):
    import cv2
    if image is None or image.size == 0 or not math.isfinite(float(min_side)) or min_side < 0:
        raise ValueError('OCR requires a nonempty image and nonnegative min_side')
    if preprocess not in {'none', 'gray', 'clahe'}:
        raise ValueError('Unknown OCR preprocessing')
    height, width = image.shape[:2]
    scale = max(1.0, min(3.0, min_side/min(height, width), math.sqrt(4_000_000/(height*width))))
    prepared = image
    if scale > 1:
        prepared = cv2.resize(image, (round(width*scale), round(height*scale)), interpolation=cv2.INTER_CUBIC)
    if preprocess != 'none':
        gray = cv2.cvtColor(prepared, cv2.COLOR_BGR2GRAY) if prepared.ndim == 3 else prepared
        prepared = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray) if preprocess == 'clahe' else gray
    return prepared, prepared.shape[1]/width, prepared.shape[0]/height


def recognize(image, model_dir, user_dir, device='cpu', *, min_side=0, preprocess='none', allowlist=None):
    prepared, sx, sy = _prepare_image(image, min_side, preprocess)
    model_dir, user_dir = Path(model_dir).resolve(), Path(user_dir).resolve()
    user_dir.mkdir(parents=True, exist_ok=True)
    signature = tuple((name, (model_dir/name).stat().st_size, (model_dir/name).stat().st_mtime_ns)
                      for name in ('craft_mlt_25k.pth', 'english_g2.pth') if (model_dir/name).is_file())
    reader = _reader(str(model_dir), str(user_dir), str(device), signature)
    options = {'paragraph': False}
    if allowlist is not None:
        options['allowlist'] = allowlist
    height, width = image.shape[:2]
    return [{'text': text, 'confidence': float(confidence),
             'bbox': [[max(0.0,min(float(width),float(x)/sx)), max(0.0,min(float(height),float(y)/sy))] for x,y in bbox]}
            for bbox,text,confidence in reader.readtext(prepared, **options)]
