import pyttsx3


class SpeechService:
    def __init__(self, engine=None):
        self.engine = engine or pyttsx3.init()

    def speak(self, text, language):
        self.engine.setProperty("voice", self._voice_for(language))
        self.engine.say(text)
        self.engine.runAndWait()

    def _voice_for(self, language):
        language_markers = {
            "English": ("en", "English"),
            "German": ("de", "German"),
        }
        markers = language_markers.get(language)
        if markers:
            for voice in self.engine.getProperty("voices"):
                if markers[0] in voice.languages or markers[1] in voice.name:
                    return voice.id
        return self.engine.getProperty("voice")
