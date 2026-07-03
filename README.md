# 🧠 StudySage — Offline/Online AI Note Assistant

Transform notes, PDFs, and screenshots into crisp summaries and smart MCQs. Use it as a web app, Telegram bot, desktop GUI, or CLI — all powered by the same core engine.

<p align="center">
  <a href="https://studysage-sahaj33.streamlit.app/" target="_blank">
    <img src="https://img.shields.io/badge/Streamlit-App-ff4b4b?logo=streamlit" />
  </a>
  <img src="https://img.shields.io/badge/Python-3.10+-blue" />
  <img src="https://img.shields.io/badge/Offline%20AI-Yes-green" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-brightgreen" /></a>
</p>

## ✨ Features

- **Summarize** text/PDFs/images (OCR) — offline or via Hugging Face API  
- **Generate quizzes** (MCQs with distractors)  
- **Advanced OCR**: images, scanned PDFs, screen photos; language auto-detect (Tesseract)  
- **Export to PDF** for summaries & quizzes  
- **Four interfaces**: Streamlit web, Telegram bot, GUI, CLI

---

## 📁 Recommended Repository Structure

```

StudySage/
├─ assets/
│  └─ images/
│     ├─ logo.png
│     └─ logo-black.png
├─ core/                     # single source of truth for business logic
│  ├─ export\_pdf.py
│  ├─ ocr\_reader.py
│  ├─ quiz\_gen.py
│  ├─ summarize.py
│  └─ **init**.py
├─ apps/
│  ├─ streamlit\_app/
│  │  └─ app.py
│  ├─ gui/
│  │  └─ gui.py
│  ├─ cli/
│  │  └─ main.py
│  └─ telegram\_bot/
│     ├─ telegram\_bot.py
│     ├─ bot\_config.sample.json
│     └─ requirements.txt
├─ config.py                 # Centralized configuration
├─ models/                   # auto-downloaded (gitignored)
├─ output/                   # generated files (gitignored)
├─ requirements.txt          # core + web/gui/cli deps
├─ packages.txt              # system packages (e.g., tesseract)
├─ LICENSE
└─ README.md

````

**Why this layout?**  
- One **`core/`** package reused everywhere (no duplication).  
- Each interface lives under **`apps/`** with its own entry file.  
- All images under **`assets/images/`** (no “where is the logo?!” chaos).  

---

## 🚀 Quick Start

### 1) Clone & set up
```bash
git clone https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant.git
cd StudySage-Offline-Online-AI-Note-Assistant
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
````

### 2) Tesseract OCR

* Windows: install from UB Mannheim build and ensure it’s on PATH
* macOS: `brew install tesseract`
* Linux: `sudo apt install tesseract-ocr`

### 3) Interfaces

#### 🌐 Streamlit (web)

```bash
streamlit run apps/streamlit_app/app.py
```

#### 🤖 Telegram Bot

```bash
cd apps/telegram_bot
cp bot_config.sample.json bot_config.json
# put your Bot Token + (optional) HF token in bot_config.json
pip install -r requirements.txt
python telegram_bot.py
```

#### 🖥️ GUI

```bash
python apps/gui/gui.py
```

#### 💻 CLI

```bash
python apps/cli/main.py
```

---

## ⚙️ Modes & Limits

| Mode    | Internet | Privacy | Speed    | Typical Limits                  |
| ------- | -------- | ------- | -------- | ------------------------------- |
| Offline | ❌        | 🔒      | ◻︎◻︎◻︎   | up to \~20k words               |
| Online  | ✅        | API     | ◻︎◻︎◻︎◻︎ | \~800 words / 4k chars per call |

Set Hugging Face token for online mode.

---

## 🧠 Core APIs

* `core.summarize.summarize_text(text, min_len, max_len)`
* `core.quiz_gen.generate_questions(summary, num_questions)`
* `core.ocr_reader.extract_text_from_image(path, lang="auto")`
* `core.export_pdf.export_summary_to_pdf(text)` / `export_quiz_to_pdf(questions)`

---

## 🧪 Development

```bash
pip install -r requirements.txt
pip install black flake8 pytest
black .
flake8
pytest
```

---

## 🛡️ Privacy

* Offline mode never sends your data out.
* Online mode uses Hugging Face Inference API.

---

## 🪪 License

- MIT — see [LICENSE](LICENSE).

