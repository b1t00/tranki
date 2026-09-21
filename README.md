# Translate & Anki

## About

**Translate & Anki**, or **"Tranki"**, is a small translation app for translating and direktly creating Anki flashcards. It comes with a range of features designed to make creating flashcards quick and easy. It includes features like screenshot-to-text (OCR), voice input and transcription, audio cards and AI-powered context checking to translate and improve cards based on a given context. 
I wanted to experiment with all kinds of techniques and tools while building a small translation app.

> **Platform:** macOS only for now. Support for other platforms is coming soon.

<img width="474" height="313" alt="grafik" src="https://github.com/user-attachments/assets/4926ddfa-b89b-47ae-876c-ac509287b787" />

## Features

### Translation
Translate text between German and English using the `googletrans` Python
library, which accesses Google Translate.

The app detects the input language automatically and translates German to
English or English to German. More languages are planned.

### Anki deck creation
Create Anki decks and save cards as `.apkg` packages for import into Anki.
The app uses the `genanki` Python library to generate the packages. Open
Settings to enter a new deck name, create a new deck, or select and switch to
an existing `.apkg` deck.

### Automatic language detection
The app automatically detects the language of the entered text, but automatic
detection can be disabled.

### Voice input and transcription
Record speech through the microphone with `sounddevice` at 16 kHz and
transcribe it locally with `faster-whisper`. The app uses the Whisper `base`
model with CPU-based `int8` computation, then sends the transcribed text for
translation.

### Text-to-speech
Uses the system voice engine to read the input and translation aloud.

### Audio on cards
Add generated English audio and personal microphone recordings to Anki cards.
The generated audio uses `gTTS` (Google Text-to-Speech) and creates two MP3
variants: US English (`tld="us"`) and Nigerian English (`tld="com.ng"`).
Personal microphone recordings are saved as mono 16-bit WAV files and added
to the corresponding Anki card.

### Screenshot OCR
Select an area of the macOS screen using the built-in `screencapture`
command. The selected area is saved temporarily as a PNG file, opened with
`Pillow`, and processed locally with `pytesseract` and the Tesseract OCR
engine. OCR runs with the `eng+deu` language data to recognize English and
German text, and the temporary screenshot is deleted afterwards.

### AI assistance
Optionally review and refine translations with Google Gemini through the
`google-generativeai` Python SDK. Enter the Gemini API key and an optional
translation context in the app's Settings window. The context is added to the
AI prompt to help with terms, situations, or preferred wording. The app
automatically discovers available Gemini models and prefers lightweight Flash
models when available.

### Window settings
Save the app window size and position in Settings. The app restores these
values on the next launch, so the window opens at the same size and location.

## Installation
Download the latest macOS app from the [Releases](../../releases) page. For screenshot text recognition, install Tesseract as well:

```bash
brew install tesseract
```

On first launch, allow **Screen Recording** and **Microphone** access in the macOS system settings.

You can also run the app from source:

```bash
python3 -m venv env
source env/bin/activate
pip install -r src/requirements.txt
python src/main.py
```

The app is mostly **vibe coded** using **GitHub Copilot Agents**.
