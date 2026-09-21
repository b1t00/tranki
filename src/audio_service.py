import hashlib
import os
import wave

import numpy as np
from gtts import gTTS


class AudioService:
    def __init__(self, media_folder):
        self.media_folder = media_folder
        os.makedirs(media_folder, exist_ok=True)

    def create_english_audio(self, text):
        if not text:
            return text, []

        hash_value = hashlib.md5(text.encode()).hexdigest()[:8]
        audio_variants = [("us", "us"), ("ng", "com.ng")]
        sound_tags = []
        media_files = []
        for suffix, tld in audio_variants:
            filename = f"english_{hash_value}_{suffix}.mp3"
            path = os.path.join(self.media_folder, filename)
            gTTS(text, lang="en", tld=tld).save(path)
            if not os.path.exists(path):
                raise OSError(f"MP3 was not created: {path}")
            media_files.append(filename)
            sound_tags.append(f"[sound:{filename}]")

        return f"{text} {' '.join(sound_tags)}", media_files

    def save_recording(self, audio, sample_rate):
        """Writes a raw mic recording (float32 ndarray, -1..1) as WAV and returns its sound tag."""
        hash_value = hashlib.md5(audio.tobytes()).hexdigest()[:8]
        filename = f"recording_{hash_value}.wav"
        path = os.path.join(self.media_folder, filename)
        self._write_wav(path, audio, sample_rate)
        return f"[sound:{filename}]"

    @staticmethod
    def _write_wav(path, audio, sample_rate):
        pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())

    def all_media_files(self):
        return [
            os.path.join(self.media_folder, filename)
            for filename in os.listdir(self.media_folder)
            if filename.endswith(".mp3") or filename.endswith(".wav")
        ]
