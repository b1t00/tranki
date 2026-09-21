import time

from googletrans import Translator


class TranslationService:
    def __init__(self, translator=None):
        self.translator = translator or Translator()

    def detect_and_translate(self, text):
        detected = self._run_request(lambda: self.translator.detect(text))
        if detected.lang == "de":
            source, destination = "de", "en"
        else:
            source, destination = "en", "de"
        result = self._run_request(
            lambda: self.translator.translate(text, src=source, dest=destination)
        )
        return detected.lang, result.text

    def translate(self, text, source, destination):
        result = self._run_request(
            lambda: self.translator.translate(text, src=source, dest=destination)
        )
        return result.text

    def _run_request(self, request):
        last_error = None
        for attempt in range(2):
            try:
                return request()
            except Exception as error:
                last_error = error
                if attempt == 0 and self.is_timeout_error(error):
                    time.sleep(0.6)
                    continue
                raise
        raise last_error

    @staticmethod
    def is_timeout_error(error):
        message = str(error).lower()
        return "timed out" in message or "timeout" in message
