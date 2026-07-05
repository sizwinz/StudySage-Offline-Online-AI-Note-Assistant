# telegram_bot.py
import sys
from pathlib import Path

# Make repo root importable before any core imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import os
import logging
import tempfile
import html
import asyncio
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# --- use shared core modules (do NOT import from apps/cli) ---
from core.io import process_file, load_text_from_file
from core.quiz_gen import generate_questions
from core.export_pdf import export_summary_to_pdf, export_quiz_to_pdf

# optional: prewarm offline model if available
try:
    from core.summarize import get_model_path  # if you exposed it from core
except Exception:
    get_model_path = None

import json

# load .env first (if present)
load_dotenv()

# Import configuration
try:
    from config import OUTPUT_DIR
except ImportError:
    OUTPUT_DIR = "output"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CONFIG_FILE = "bot_config.json"
from pathlib import Path as _P
OUTPUT_DIR_PATH = _P(OUTPUT_DIR)
OUTPUT_DIR_PATH.mkdir(exist_ok=True)

def _escape(s: str) -> str:
    return html.escape(s or "")

def _kb(rows):
    return InlineKeyboardMarkup(rows)

def _processing_kb():
    return _kb([
        [InlineKeyboardButton("📝 Generate Summary", callback_data='process_summary')],
        [InlineKeyboardButton("🧪 Create Quiz", callback_data='process_quiz')],
        [InlineKeyboardButton("🔍 Extract Text (OCR)", callback_data='process_ocr')],
        [InlineKeyboardButton("🔬 OCR (Aggressive)", callback_data='process_ocr_aggr')],
        [InlineKeyboardButton("📋 Summary + Quiz", callback_data='process_both')],
        [InlineKeyboardButton("🗑️ Cancel", callback_data='cancel_processing')]
    ])

class StudySageBot:
    def __init__(self):
        self.config = self.load_config()
        self.user_sessions = {}  # user_id -> session dict

        # override with env variables if provided
        env_bot = os.getenv("BOT_TOKEN")
        env_hf = os.getenv("HF_API_KEY")
        if env_bot:
            self.config['bot_token'] = env_bot
        if env_hf:
            self.config['hf_api_key'] = env_hf

    def load_config(self):
        if Path(CONFIG_FILE).exists():
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {
            "bot_token": "",
            "hf_api_key": "",
            "default_mode": "offline",
            "max_file_size": 20 * 1024 * 1024
        }

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    # ---- utility to get chat id ----
    def _chat_id(self, update: Update):
        if update.effective_chat:
            return update.effective_chat.id
        if update.callback_query and update.callback_query.message:
            return update.callback_query.message.chat.id
        return None

    # ---- basic UI text helpers ----
    async def _send_html(self, context, chat_id, text, keyboard=None):
        return await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    # ---- commands ----
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = self._chat_id(update)

        welcome_text = (
            f"<b>Welcome to StudySage Bot, {_escape(user.first_name)}!</b>\n\n"
            "I'm your AI-powered study assistant. I can help you:\n\n"
            "📝 <b>Summarize</b> documents and notes\n"
            "🧪 <b>Generate quiz</b> questions from your content\n"
            "🔍 <b>Extract text</b> from images (OCR)\n"
            "📄 <b>Export</b> results as PDF\n\n"
            "<b>Getting Started:</b>\n• Send any document (PDF, TXT, images)\n• Use /help for detailed commands\n• Configure settings with /settings"
        )

        keyboard = _kb([
            [InlineKeyboardButton("📖 How to Use", callback_data='help')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='settings')],
            [InlineKeyboardButton("📊 Examples", callback_data='examples')],
            [InlineKeyboardButton("📁 GitHub Repository", url="https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant")]
        ])
        await self._send_html(context, chat_id, welcome_text, keyboard)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        help_text = (
            "🆘 <b>StudySage Bot Help</b>\n\n"
            "• Send PDF/TXT/MD or images (OCR)\n"
            "• Max file size: 20MB\n\n"
            "Commands:\n"
            "/start /help /settings /status /clear /mode\n"
            "Use '/mode offline' or '/mode online' to switch processing mode.\n\n"
            "After processing:\n"
            "• <b>📄 Export Summary PDF</b> or <b>📄 Export Quiz PDF</b>\n"
            "• <b>📋 View All Questions</b> for the full quiz"
        )
        keyboard = _kb([
            [InlineKeyboardButton("⚙️ Settings", callback_data='settings')],
            [InlineKeyboardButton("🏠 Back to Start", callback_data='start')]
        ])
        await self._send_html(context, chat_id, help_text, keyboard)

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        current_mode = self.user_sessions.get(user_id, {}).get('mode', self.config['default_mode'])
        settings_text = (
            "⚙️ <b>Settings</b>\n\n"
            f"<b>Current Mode:</b> <code>{_escape(current_mode)}</code>\n"
            f"<b>API Status:</b> {'✅ Configured' if self.config.get('hf_api_key') else '❌ Not Set'}\n\n"
            "Processing Modes:\n"
            "• Offline — private, no API needed\n"
            "• Online — faster, requires Hugging Face API key (/setapi)\n\n"
            "Tip: set API with /setapi &lt;YOUR_API_KEY&gt;"
        )
        keyboard = _kb([
            [
                InlineKeyboardButton("🔄 Offline", callback_data='mode_offline'),
                InlineKeyboardButton("🌐 Online", callback_data='mode_online')
            ],
            [InlineKeyboardButton("🏠 Back to Start", callback_data='start')]
        ])
        await self._send_html(context, chat_id, settings_text, keyboard)

    async def examples_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        examples_text = (
            "📊 <b>Examples</b>\n\n"
            "• Upload notes.txt → tap <b>📝 Generate Summary</b>\n"
            "• Tap <b>🧪 Create Quiz</b> → get MCQs\n"
            "• Send a screenshot → tap <b>🔍 Extract Text (OCR)</b>\n"
            "• Tap <b>📄 Export Summary/Quiz PDF</b> to download"
        )
        keyboard = _kb([[InlineKeyboardButton("🏠 Back to Start", callback_data='start')]])
        await self._send_html(context, chat_id, examples_text, keyboard)

    # ---- session management commands ----
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        session = self.user_sessions.get(user_id, {})
        file_name = session.get('file_name') or "None"
        has_summary = bool(session.get('summary'))
        has_quiz = bool(session.get('quiz'))
        mode = session.get('mode', self.config.get('default_mode', 'offline'))
        text = (
            "📦 <b>Session Status</b>\n\n"
            f"<b>File:</b> <code>{_escape(file_name)}</code>\n"
            f"<b>Summary:</b> {'✅' if has_summary else '❌'}\n"
            f"<b>Quiz:</b> {'✅' if has_quiz else '❌'}\n"
            f"<b>Mode:</b> <code>{_escape(mode)}</code>\n"
        )
        await self._send_html(context, chat_id, text, _processing_kb())

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        session = self.user_sessions.pop(user_id, {})
        try:
            fp = session.get('file_path')
            if fp and os.path.exists(fp):
                os.unlink(fp)
        except Exception:
            pass
        await self._send_html(context, self._chat_id(update), "🧹 Cleared session. Send a new file to start.", _processing_kb())

    async def mode_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        if not context.args:
            await self._send_html(context, chat_id, "Usage: /mode &lt;offline|online&gt;")
            return
        mode = context.args[0].lower().strip()
        if mode not in ("offline", "online"):
            await self._send_html(context, chat_id, "❌ Invalid mode. Use 'offline' or 'online'.")
            return
        self.user_sessions.setdefault(user_id, {})['mode'] = mode
        await self._send_html(context, chat_id, f"✅ Mode set to <b>{_escape(mode)}</b>.", _processing_kb())

    async def set_api_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        if not context.args:
            await self._send_html(context, chat_id, "Usage: /setapi &lt;HuggingFace API Key&gt;")
            return
        self.config['hf_api_key'] = context.args[0].strip()
        self.save_config()
        await self._send_html(context, chat_id, "✅ API key saved.")

    # ---- file handlers ----
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        doc = update.message.document
        max_size = int(self.config.get('max_file_size', 20 * 1024 * 1024))
        if doc.file_size > max_size:
            await self._send_html(context, chat_id, "❌ File too large. Max 20MB.")
            return

        file = await context.bot.get_file(doc.file_id)
        suffix = Path(doc.file_name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            await file.download_to_drive(tmp.name)
            self.user_sessions[user_id] = {
                "file_path": tmp.name,
                "file_name": doc.file_name,
                "summary": None,
                "quiz": None,
                "mode": self.user_sessions.get(user_id, {}).get('mode', self.config.get('default_mode', 'offline'))
            }
        await self._send_html(context, chat_id, f"📂 <b>Received:</b> <code>{_escape(doc.file_name)}</code>\nChoose an action:", _processing_kb())

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        photos = update.message.photo
        if not photos:
            await self._send_html(context, chat_id, "❌ No photo found.")
            return
        file = await context.bot.get_file(photos[-1].file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            await file.download_to_drive(tmp.name)
            self.user_sessions[user_id] = {
                "file_path": tmp.name,
                "file_name": "photo.jpg",
                "summary": None,
                "quiz": None,
                "mode": self.user_sessions.get(user_id, {}).get('mode', self.config.get('default_mode', 'offline'))
            }
        await self._send_html(context, chat_id, "🖼️ Image saved. Choose an action:", _processing_kb())

    # ---- processing actions ----
    async def process_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        session = self.user_sessions.get(user_id, {})

        if not session.get('file_path'):
            await self._send_html(context, chat_id, "❌ No file found. Please upload a file first.", _processing_kb())
            return

        status_msg = await context.bot.send_message(chat_id, "⏳ Generating summary...")

        try:
            mode = session.get('mode', 'offline')
            api_key = self.config.get('hf_api_key') if mode == 'online' else None

            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(
                None,
                lambda: process_file(session['file_path'], mode=mode, api_key=api_key, min_length=30, max_length=200)
            )
            self.user_sessions[user_id]['summary'] = summary

            summary_text = (
                "📝 <b>Summary Generated</b>\n\n"
                f"{_escape(summary)}\n\n"
                f"<i>Words:</i> {len(summary.split())} | <i>Mode:</i> {_escape(mode)}"
            )
            await self._send_html(
                context,
                chat_id,
                summary_text,
                _kb([
                    [InlineKeyboardButton("📄 Export Summary PDF", callback_data='export_summary_pdf')],
                    [InlineKeyboardButton("🧪 Create Quiz", callback_data='process_quiz')],
                    [InlineKeyboardButton("🏠 New File", callback_data='start')]
                ])
            )

            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="✅ Summary ready.")
            except Exception:
                pass

        except Exception as e:
            logger.exception("Error processing summary")
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ Failed: {_escape(str(e))}")
            except Exception:
                pass
            await self._send_html(context, chat_id, f"❌ Error generating summary: {_escape(str(e))}", _processing_kb())

    async def process_quiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()
        chat_id = self._chat_id(update)
        user_id = update.effective_user.id
        session = self.user_sessions.get(user_id, {})

        if not session.get('summary') and not session.get('file_path'):
            await self._send_html(context, chat_id, "❌ No file/summary available. Upload a file first.", _processing_kb())
            return

        status_msg = await context.bot.send_message(chat_id, "⏳ Generating quiz...")

        try:
            loop = asyncio.get_running_loop()

            if not session.get('summary'):
                mode = session.get('mode', 'offline')
                api_key = self.config.get('hf_api_key') if mode == 'online' else None
                summary = await loop.run_in_executor(
                    None,
                    lambda: process_file(session['file_path'], mode=mode, api_key=api_key, min_length=30, max_length=200)
                )
                self.user_sessions[user_id]['summary'] = summary

            summary = self.user_sessions[user_id]['summary']

            questions = await loop.run_in_executor(None, lambda: generate_questions(summary, num_questions=5))
            if not questions:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ Couldn't generate questions.")
                await self._send_html(context, chat_id, "❌ Couldn't generate quiz questions. Try a longer/clearer document.", _processing_kb())
                return

            self.user_sessions[user_id]['quiz'] = questions

            lines = ["🧪 <b>Quiz Generated</b>\n"]
            for i, q in enumerate(questions[:3], 1):
                lines.append(f"<b>Q{i}.</b> {_escape(q['question'])}")
                for j, opt in enumerate(q['options'], 1):
                    lines.append(f"{j}. {_escape(opt)}")
                lines.append(f"✅ <i>Answer:</i> {_escape(q['answer'])}\n")
            if len(questions) > 3:
                lines.append(f". and {len(questions) - 3} more questions")
            lines.append(f"<i>Total Questions:</i> {len(questions)}")

            await self._send_html(
                context,
                chat_id,
                "\n".join(lines),
                _kb([
                    [InlineKeyboardButton("📋 View All Questions", callback_data='view_all_questions')],
                    [InlineKeyboardButton("📄 Export Quiz PDF", callback_data='export_quiz_pdf')],
                    [InlineKeyboardButton("🏠 New File", callback_data='start')]
                ])
            )

            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="✅ Quiz ready.")
            except Exception:
                pass

        except Exception as e:
            logger.exception("Error generating quiz")
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ Failed: {_escape(str(e))}")
            except Exception:
                pass
            await self._send_html(context, chat_id, f"❌ Error generating quiz: {_escape(str(e))}", _processing_kb())

    async def view_all_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text="Sending all questions.")
        user_id = query.from_user.id
        session = self.user_sessions.get(user_id, {})
        questions = session.get('quiz')
        if not questions:
            await query.message.reply_text("❌ No quiz available. Generate one first.", reply_markup=_processing_kb())
            return

        buf = []
        chunks = []
        for i, q in enumerate(questions, 1):
            buf.append(f"<b>Q{i}.</b> {_escape(q['question'])}")
            for j, opt in enumerate(q['options'], 1):
                buf.append(f"{j}. {_escape(opt)}")
            buf.append(f"✅ <i>Answer:</i> {_escape(q['answer'])}\n")
            if sum(len(x) for x in buf) > 3000:
                chunks.append("\n".join(buf)); buf = []
        if buf:
            chunks.append("\n".join(buf))

        for ch in chunks:
            await self._send_html(context, self._chat_id(update), ch)

        await self._send_html(context, self._chat_id(update), "✅ Sent all questions above. What next?", _processing_kb())

    async def process_ocr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text="Running OCR...")
        chat_id = self._chat_id(update)
        user_id = query.from_user.id
        session = self.user_sessions.get(user_id, {})
        file_path = session.get('file_path')
        if not file_path:
            await query.message.reply_text("❌ No file found. Upload an image or PDF first.", reply_markup=_processing_kb())
            return

        status_msg = await context.bot.send_message(chat_id, "▶️ OCR started…")
        loop = asyncio.get_running_loop()

        try:
            text = await loop.run_in_executor(None, lambda: load_text_from_file(file_path))
            if not text.strip():
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="⛔ OCR done (no readable text).")
                except Exception:
                    pass
                await query.message.reply_text("❌ OCR found no readable text. Try a clearer image.", reply_markup=_processing_kb())
                return

            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="✅ OCR done.")
            except Exception:
                pass

            preview = text[:1500] + ("." if len(text) > 1500 else "")
            msg = (
                "🧾 <b>OCR Result (preview)</b>\n\n"
                f"<code>{_escape(preview)}</code>\n\n"
                f"<i>Characters:</i> {len(text)}"
            )
            await self._send_html(
                context,
                chat_id,
                msg,
                _kb([
                    [InlineKeyboardButton("📝 Summarize OCR Text", callback_data='process_summary')],
                    [InlineKeyboardButton("🏠 Back", callback_data='start')]
                ])
            )
        except Exception as e:
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ OCR failed.")
            except Exception:
                pass
            logger.exception("Error in process_ocr")
            await query.message.reply_text(f"❌ OCR error: {_escape(str(e))}", reply_markup=_processing_kb())

    async def process_ocr_aggressive(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text="Running OCR (Aggressive)...")
        chat_id = self._chat_id(update)
        user_id = query.from_user.id
        session = self.user_sessions.get(user_id, {})
        file_path = session.get('file_path')
        if not file_path:
            await query.message.reply_text("❌ No file found. Upload an image or PDF first.", reply_markup=_processing_kb())
            return

        status_msg = await context.bot.send_message(chat_id, "▶️ OCR (Aggressive) started…")
        loop = asyncio.get_running_loop()

        try:
            text = await loop.run_in_executor(None, lambda: load_text_from_file(file_path, lang="auto", progress_callback=None, force_ocr=True))
            if not text.strip():
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="⛔ OCR (Aggressive) done (no readable text).")
                except Exception:
                    pass
                await query.message.reply_text("❌ OCR found no readable text. Try a clearer image or a native screenshot.", reply_markup=_processing_kb())
                return

            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="✅ OCR (Aggressive) done.")
            except Exception:
                pass

            preview = text[:1500] + ("." if len(text) > 1500 else "")
            msg = (
                "🧾 <b>OCR Result (Aggressive, preview)</b>\n\n"
                f"<code>{_escape(preview)}</code>\n\n"
                f"<i>Characters:</i> {len(text)}"
            )
            await self._send_html(
                context,
                chat_id,
                msg,
                _kb([
                    [InlineKeyboardButton("📝 Summarize OCR Text", callback_data='process_summary')],
                    [InlineKeyboardButton("🏠 Back", callback_data='start')]
                ])
            )
        except Exception as e:
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ OCR (Aggressive) failed.")
            except Exception:
                pass
            logger.exception("Error in process_ocr_aggressive")
            await query.message.reply_text(f"❌ OCR error: {_escape(str(e))}", reply_markup=_processing_kb())

    async def export_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text="Preparing PDF.")
        user_id = query.from_user.id
        session = self.user_sessions.get(user_id, {})
        export_type = query.data.split('_')[1]  # 'summary' or 'quiz'
        try:
            if export_type == 'summary' and session.get('summary'):
                pdf_path = export_summary_to_pdf(session['summary'])
                caption = "📝 Summary PDF"
            elif export_type == 'quiz' and session.get('quiz'):
                pdf_path = export_quiz_to_pdf(session['quiz'])
                caption = "🧪 Quiz PDF"
            else:
                await query.message.reply_text("❌ No content to export.", reply_markup=_processing_kb())
                return

            with open(pdf_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=self._chat_id(update),
                    document=f,
                    filename=os.path.basename(pdf_path),
                    caption=caption
                )
            await query.message.reply_text("✅ PDF exported successfully.", reply_markup=_processing_kb())
            try:
                os.unlink(pdf_path)
            except Exception:
                pass
        except Exception as e:
            logger.exception("Error in export_pdf")
            await query.message.reply_text(f"❌ Error exporting PDF: {_escape(str(e))}", reply_markup=_processing_kb())

    # central callback router
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        if data == 'help':
            await self.help_command(update, context)
        elif data == 'settings':
            await self.settings_command(update, context)
        elif data == 'examples':
            await self.examples_command(update, context)
        elif data == 'start':
            await self.start(update, context)
        elif data.startswith('mode_'):
            new_mode = data.split('_', 1)[1]
            context.args = [new_mode]
            await self.mode_command(update, context)
        elif data == 'process_summary':
            await self.process_summary(update, context)
        elif data == 'process_quiz':
            await self.process_quiz(update, context)
        elif data == 'process_ocr':
            await self.process_ocr(update, context)
        elif data == 'process_ocr_aggr':
            await self.process_ocr_aggressive(update, context)
        elif data == 'process_both':
            if query:
                await query.answer()
            chat_id = self._chat_id(update)
            user_id = update.effective_user.id
            session = self.user_sessions.get(user_id, {})
            if not session.get('file_path'):
                await self._send_html(context, chat_id, "❌ No file found. Please upload a file first.", _processing_kb())
                return

            status_msg = await context.bot.send_message(chat_id, "⏳ Generating summary and quiz...")

            try:
                loop = asyncio.get_running_loop()
                mode = session.get('mode', 'offline')
                api_key = self.config.get('hf_api_key') if mode == 'online' else None

                summary = await loop.run_in_executor(
                    None,
                    lambda: process_file(session['file_path'], mode=mode, api_key=api_key, min_length=30, max_length=200)
                )
                self.user_sessions[user_id]['summary'] = summary

                summary_text = (
                    "📝 <b>Summary Generated</b>\n\n"
                    f"{_escape(summary)}\n\n"
                    f"<i>Words:</i> {len(summary.split())} | <i>Mode:</i> {_escape(mode)}"
                )
                await self._send_html(
                    context,
                    chat_id,
                    summary_text,
                    _kb([
                        [InlineKeyboardButton("📄 Export Summary PDF", callback_data='export_summary_pdf')],
                        [InlineKeyboardButton("🧪 Create Quiz", callback_data='process_quiz')]
                    ])
                )

                questions = await loop.run_in_executor(None, lambda: generate_questions(summary, num_questions=5))
                if not questions:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ Couldn't generate questions.")
                    await self._send_html(context, chat_id, "❌ Couldn't generate quiz questions. Try a longer/clearer document.", _processing_kb())
                    return

                self.user_sessions[user_id]['quiz'] = questions

                lines = ["🧪 <b>Quiz Generated</b>\n"]
                for i, q in enumerate(questions[:3], 1):
                    lines.append(f"<b>Q{i}.</b> {_escape(q['question'])}")
                    for j, opt in enumerate(q['options'], 1):
                        lines.append(f"{j}. {_escape(opt)}")
                    lines.append(f"✅ <i>Answer:</i> {_escape(q['answer'])}\n")
                if len(questions) > 3:
                    lines.append(f". and {len(questions)-3} more questions")
                lines.append(f"<i>Total Questions:</i> {len(questions)}")

                await self._send_html(
                    context,
                    chat_id,
                    "\n".join(lines),
                    _kb([
                        [InlineKeyboardButton("📋 View All Questions", callback_data='view_all_questions')],
                        [InlineKeyboardButton("📄 Export Quiz PDF", callback_data='export_quiz_pdf')],
                        [InlineKeyboardButton("🏠 New File", callback_data='start')]
                    ])
                )

                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="✅ Summary & Quiz ready.")
                except Exception:
                    pass

            except Exception as e:
                logger.exception("Error in process_both")
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ Failed: {_escape(str(e))}")
                except Exception:
                    pass
                await self._send_html(context, chat_id, f"❌ Error: {_escape(str(e))}", _processing_kb())
        elif data == 'view_all_questions':
            await self.view_all_questions(update, context)
        elif data.startswith('export_'):
            await self.export_pdf(update, context)
        elif data == 'cancel_processing':
            await query.answer(text="Cancelled.")
            await query.message.reply_text("❌ Processing cancelled. Send a new file to start over.", reply_markup=_processing_kb())
        else:
            await query.answer(text="Unknown action")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.effective_chat:
                await self._send_html(context, self._chat_id(update), "❌ An unexpected error occurred. Please try again.")
        except Exception:
            pass

def main():
    bot = StudySageBot()

    # Pre-warm offline model to avoid first-use stall
    try:
        if bot.config.get('default_mode', 'offline') == 'offline':
            get_model_path()
    except Exception:
        pass

    if not bot.config.get('bot_token'):
        token = input("Enter your Telegram Bot Token: ").strip()
        bot.config['bot_token'] = token
        bot.save_config()

    application = Application.builder().token(bot.config['bot_token']).build()

    # command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("settings", bot.settings_command))
    application.add_handler(CommandHandler("examples", bot.examples_command))
    application.add_handler(CommandHandler("setapi", bot.set_api_key))
    application.add_handler(CommandHandler("status", bot.status_command))
    application.add_handler(CommandHandler("clear", bot.clear_command))
    application.add_handler(CommandHandler("mode", bot.mode_command))

    # files / photos
    application.add_handler(MessageHandler(filters.Document.ALL, bot.handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, bot.handle_photo))

    # callback router
    application.add_handler(CallbackQueryHandler(bot.button_handler))

    # error handler
    application.add_error_handler(bot.error_handler)

    print("🤖 StudySage Bot is starting.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()