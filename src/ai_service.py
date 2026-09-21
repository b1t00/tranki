import google.generativeai as genai
from google.api_core.exceptions import NotFound


DEFAULT_AI_CONTEXT = (
    "The translations are used for English-German Anki vocabulary cards. "
    "Check the existing translation for accuracy and natural language use. "
    "Pay particular attention to correct tense and aspect, modal verbs. "
    "Expressions and idioms must not be translated literally. "
    "Consider differences in register, from colloquial to formal. "
    "Keep the translation as short and natural as the original, "
    "without unnecessary additions or explanations."
)


class AIService:
    """Wraps the Gemini API to refine translations with extra context."""

    def __init__(self, api_key="", context=""):
        self.api_key = api_key
        self.context = context
        self._candidate_models = []
        self._working_model_name = None
        if api_key:
            self.configure(api_key)

    def configure(self, api_key):
        self.api_key = api_key
        self._candidate_models = []
        self._working_model_name = None
        if api_key:
            genai.configure(api_key=api_key)
            self._candidate_models = self._list_candidate_models()

    @staticmethod
    def _list_candidate_models():
        """List available models, with the cheapest/lite models first."""
        excluded_keywords = ("live", "transcribe", "tts", "audio", "image", "embedding")
        candidates = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
            and not any(keyword in m.name.lower() for keyword in excluded_keywords)
        ]
        if not candidates:
            raise RuntimeError("No usable Gemini model found for this API key.")

        def rank(name):
            lower = name.lower()
            if "flash-lite" in lower:
                return 0
            if "flash" in lower:
                return 1
            return 2

        # Sort newest versions first, then apply the cost ranking (lite > flash > rest).
        by_newest = sorted(candidates, reverse=True)
        return sorted(by_newest, key=rank)

    def set_context(self, context):
        self.context = context

    @property
    def is_configured(self):
        return bool(self._candidate_models)

    def refine_translation(self, source_text, translated_text, src_lang, dest_lang):
        if not self.is_configured:
            raise RuntimeError("AI service is not configured (API key is missing).")

        prompt = (
            f"You are a bilingual translation editor for {src_lang} and {dest_lang}. "
            f"Check BOTH texts: the source text ({src_lang}) and the translation ({dest_lang}). "
            f"Correct spelling, typing errors, incorrect special characters, and line breaks in both texts. "
            f"Ensure that the translation is accurate and natural, paying particular attention to tenses, "
            f"idioms, and context. Do not change the meaning of either text; only correct errors.\n\n"
            f"Reply ONLY in exactly this format, without additional explanations:\n"
            f"SOURCE_TEXT: <corrected source text>\n"
            f"TRANSLATION: <corrected translation>\n\n"
            f"Source text ({src_lang}): {source_text}\n"
            f"Current translation ({dest_lang}): {translated_text}\n"
        )
        if self.context:
            prompt += f"\nAdditional context: {self.context}\n"

        result = self._generate_with_fallback(prompt)
        if not result:
            raise RuntimeError("AI response was empty.")
        return self._parse_refined_response(result, source_text, translated_text)

    @staticmethod
    def _parse_refined_response(result, fallback_source, fallback_translation):
        """Parse source and translation blocks, preserving multiline content."""
        buffers = {"SOURCE_TEXT": [], "TRANSLATION": []}
        current_key = None
        for line in result.splitlines():
            stripped = line.strip()
            matched_key = next(
                (key for key in buffers if stripped.upper().startswith(f"{key}:")), None
            )
            if matched_key:
                current_key = matched_key
                buffers[current_key].append(stripped.split(":", 1)[1].strip())
            elif current_key:
                buffers[current_key].append(line)

        refined_source = "\n".join(buffers["SOURCE_TEXT"]).strip() or fallback_source
        refined_translation = "\n".join(buffers["TRANSLATION"]).strip() or fallback_translation
        return refined_source, refined_translation

    def _generate_with_fallback(self, prompt):
        # The model list may contain models that are no longer enabled for the key.
        names_to_try = (
            [self._working_model_name] if self._working_model_name else []
        ) + [n for n in self._candidate_models if n != self._working_model_name]

        last_error = None
        for name in names_to_try:
            try:
                model = genai.GenerativeModel(name)
                response = model.generate_content(prompt)
                self._working_model_name = name
                return (response.text or "").strip()
            except NotFound as error:
                last_error = error
                continue
        raise RuntimeError(f"No model available (last error: {last_error})")
