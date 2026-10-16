"""Raw EasyOCR text and boxes; no circuit parameter guessing or cloud calls."""

def recognize(image, model_dir, user_dir, device='cpu'):
    import easyocr
    user_dir.mkdir(parents=True, exist_ok=True)
    reader = easyocr.Reader(['en'], gpu=device != 'cpu',
                            model_storage_directory=str(model_dir),
                            user_network_directory=str(user_dir), download_enabled=False)
    return [{'text': text, 'confidence': float(confidence),
             'bbox': [[float(x), float(y)] for x, y in bbox]}
            for bbox, text, confidence in reader.readtext(image, paragraph=False)]
