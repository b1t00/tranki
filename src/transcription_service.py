import threading

import numpy as np
import sounddevice as sd


class TranscriptionService:
    """Records microphone audio while active and transcribes it locally via faster-whisper."""

    SAMPLE_RATE = 16000

    def __init__(self, model_size="base"):
        self._model_size = model_size
        self._model = None
        self._model_lock = threading.Lock()
        self._stream = None
        self._frames = []
        self._recording = False
        self._last_recording = None  # (float32 audio ndarray, sample_rate)

    def _ensure_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel
                    self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def preload_async(self, on_error=None):
        """Loads (and on first run downloads) the model in the background so recording isn't blocked by it."""
        def worker():
            try:
                self._ensure_model()
            except Exception as e:
                if on_error:
                    on_error(e)
        threading.Thread(target=worker, daemon=True).start()

    @property
    def is_recording(self):
        return self._recording

    def start_recording(self):
        if self._recording:
            return
        self._frames = []

        def callback(indata, frames, time_info, status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE, channels=1, dtype="float32", callback=callback
        )
        self._stream.start()
        self._recording = True

    def cancel_recording(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._recording = False
        self._frames = []

    def stop_and_transcribe(self, language=None):
        """Stops recording and returns the transcribed text. Blocking - call from a worker thread."""
        if not self._recording:
            return ""
        self._recording = False
        self._stream.stop()
        self._stream.close()
        self._stream = None

        frames, self._frames = self._frames, []
        if not frames:
            return ""
        audio = np.concatenate(frames, axis=0).flatten()
        if audio.size == 0:
            return ""
        self._last_recording = (audio, self.SAMPLE_RATE)

        model = self._ensure_model()
        text = self._run_transcription(model, audio, language, vad_filter=True)
        if not text:
            # VAD can incorrectly discard short or quiet recordings as silence; retry without the filter.
            text = self._run_transcription(model, audio, language, vad_filter=False)
        return text

    @staticmethod
    def _run_transcription(model, audio, language, vad_filter):
        segments, _ = model.transcribe(audio, language=language, vad_filter=vad_filter)
        return " ".join(segment.text.strip() for segment in segments).strip()

    def take_last_recording(self):
        """Returns (audio ndarray, sample_rate) of the last recording and clears it, or None."""
        recording, self._last_recording = self._last_recording, None
        return recording
