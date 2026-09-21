import os
import subprocess
import tempfile

from PIL import Image
import pytesseract


class OCRService:
    def __init__(self, tesseract_path=None):
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

    def capture_text(self, timeout=30):
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_path = temp_file.name
        temp_file.close()
        try:
            result = subprocess.run(
                ["screencapture", "-i", "-s", temp_path],
                capture_output=True,
                timeout=timeout,
            )
            if result.returncode != 0 or not os.path.exists(temp_path):
                return ""
            if os.path.getsize(temp_path) == 0:
                return ""
            return self.text_from_file(temp_path)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def text_from_file(self, image_path):
        with Image.open(image_path) as image:
            return pytesseract.image_to_string(image, lang="eng+deu").strip()
