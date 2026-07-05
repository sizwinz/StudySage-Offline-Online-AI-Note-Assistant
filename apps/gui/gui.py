import sys
from pathlib import Path

# Ensure repo root is on sys.path before core imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
import os
from PIL import Image, ImageTk

# Import configuration
try:
    from config import OUTPUT_DIR
except ImportError:
    OUTPUT_DIR = "output"

from core.summarize import summarize_text
from core.ocr_reader import extract_text_from_image
from core.export_pdf import export_summary_to_pdf, export_quiz_to_pdf
from core.io import load_text_from_file
from core.quiz_gen import generate_questions

OUTPUT_PATH = Path(OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)

# Set initial appearance and theme settings
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class StudySageApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("StudySage – AI Note Assistant")
        self.geometry("1000x650")
        self.minimum_width = 800
        self.minimum_height = 550
        self.minsize(self.minimum_width, self.minimum_height)
        
        # Set window icon photo
        logo_path = Path("assets/images/logo.png")
        if logo_path.exists():
            try:
                icon_img = ImageTk.PhotoImage(Image.open(logo_path).resize((32, 32)))
                self.iconphoto(False, icon_img)
                self._icon_img = icon_img  # Reference to avoid garbage collection
            except Exception as e:
                print(f"Error setting window icon: {e}")
        
        # State variables
        self.file_path = ""
        self.text_data = ""
        self.summary_data = ""
        self.questions = []
        self.api_mode = "offline"
        
        # Configure layout grid (1 row, 2 columns)
        # Column 0: Sidebar (fixed width), Column 1: Main Panel (responsive weight)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.build_ui()
        
    def build_ui(self):
        # 1. SIDEBAR FRAME
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=("gray90", "gray13"))
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)  # spacer row
        
        # Logo / Title Sub-frame
        self.brand_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.brand_frame.grid(row=0, column=0, padx=20, pady=(20, 2), sticky="w")
        
        logo_path = Path("assets/images/logo.png")
        if logo_path.exists():
            try:
                pil_logo = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(dark_image=pil_logo, light_image=pil_logo, size=(38, 38))
                self.logo_icon_label = ctk.CTkLabel(self.brand_frame, image=self.logo_image, text="")
                self.logo_icon_label.pack(side="left", padx=(0, 10))
            except Exception as e:
                print(f"Error loading logo in GUI: {e}")
                
        self.logo_label = ctk.CTkLabel(
            self.brand_frame, 
            text="StudySage", 
            font=ctk.CTkFont(family="Helvetica", size=22, weight="bold")
        )
        self.logo_label.pack(side="left")
        
        self.author_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="AI Note Assistant", 
            font=ctk.CTkFont(family="Helvetica", size=11),
            text_color="gray50"
        )
        self.author_label.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="w")
        
        # Section: Configuration
        self.config_title = ctk.CTkLabel(
            self.sidebar_frame, 
            text="SETTINGS", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray60", "gray50")
        )
        self.config_title.grid(row=2, column=0, padx=20, pady=(5, 2), sticky="w")
        
        # Settings Inner Container Frame (so toggle_mode doesn't shift everything in sidebar)
        self.settings_container = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.settings_container.grid(row=3, column=0, padx=20, pady=(2, 10), sticky="ew")
        
        # Mode Switcher (Offline / Online)
        self.mode_label = ctk.CTkLabel(self.settings_container, text="Processing Mode", font=ctk.CTkFont(size=11))
        self.mode_label.pack(anchor="w", pady=(2, 2))
        
        self.mode_switch = ctk.CTkSegmentedButton(
            self.settings_container,
            values=["Offline", "Online"],
            command=self.toggle_mode
        )
        self.mode_switch.pack(fill="x", pady=(0, 8))
        self.mode_switch.set("Offline")
        
        # API Key (hidden by default)
        self.api_key_entry = ctk.CTkEntry(
            self.settings_container, 
            placeholder_text="Enter HF API Key...", 
            show="*"
        )
        
        # Sliders for Summary Length
        self.len_label = ctk.CTkLabel(self.settings_container, text="Min/Max length: 30 / 150", font=ctk.CTkFont(size=11))
        self.len_label.pack(anchor="w", pady=(4, 2))
        
        self.min_slider = ctk.CTkSlider(self.settings_container, from_=10, to=100, number_of_steps=18, command=self.update_slider_label)
        self.min_slider.pack(fill="x", pady=4)
        self.min_slider.set(30)
        
        self.max_slider = ctk.CTkSlider(self.settings_container, from_=50, to=300, number_of_steps=25, command=self.update_slider_label)
        self.max_slider.pack(fill="x", pady=4)
        self.max_slider.set(150)
        
        # Section: Actions
        self.actions_title = ctk.CTkLabel(
            self.sidebar_frame, 
            text="ACTIONS", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray60", "gray50")
        )
        self.actions_title.grid(row=4, column=0, padx=20, pady=(10, 2), sticky="w")
        
        # Action Buttons container
        self.actions_container = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.actions_container.grid(row=5, column=0, padx=20, pady=2, sticky="nsew")
        self.actions_container.grid_columnconfigure(0, weight=1)
        
        self.btn_load = ctk.CTkButton(self.actions_container, text="Choose File", command=self.load_file)
        self.btn_load.grid(row=0, column=0, pady=4, sticky="ew")
        
        self.btn_ocr = ctk.CTkButton(self.actions_container, text="Extract Text (OCR)", command=self.do_ocr, fg_color=("gray75", "gray25"), text_color=("black", "white"))
        self.btn_ocr.grid(row=1, column=0, pady=4, sticky="ew")
        
        self.btn_summary = ctk.CTkButton(self.actions_container, text="Generate Summary", command=self.do_summary)
        self.btn_summary.grid(row=2, column=0, pady=4, sticky="ew")
        
        self.btn_quiz = ctk.CTkButton(self.actions_container, text="Generate Quiz", command=self.do_quiz)
        self.btn_quiz.grid(row=3, column=0, pady=4, sticky="ew")
        
        self.btn_export = ctk.CTkButton(self.actions_container, text="Export as PDF", command=self.export_pdf, fg_color="#16A34A", hover_color="#15803D")
        self.btn_export.grid(row=4, column=0, pady=4, sticky="ew")

        # Theme Switcher at bottom
        self.appearance_label = ctk.CTkLabel(self.sidebar_frame, text="Theme Mode", font=ctk.CTkFont(size=11))
        self.appearance_label.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.appearance_switch = ctk.CTkSegmentedButton(
            self.sidebar_frame,
            values=["Light", "Dark"],
            command=self.change_appearance
        )
        self.appearance_switch.grid(row=8, column=0, padx=20, pady=(2, 5), sticky="ew")
        self.appearance_switch.set("Dark")
        
        # GitHub Button at the bottom
        self.btn_github = ctk.CTkButton(
            self.sidebar_frame, 
            text="📁 GitHub Repository", 
            command=self.open_github,
            fg_color="transparent", 
            border_width=1, 
            border_color=("gray60", "gray40"),
            text_color=("black", "white"),
            hover_color=("gray85", "gray20")
        )
        self.btn_github.grid(row=9, column=0, padx=20, pady=(5, 20), sticky="ew")
        
        # 2. MAIN CONTENT AREA
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=0)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=0)
        
        # Status Label at the top
        self.status_label = ctk.CTkLabel(
            self.main_frame, 
            text="Ready. Load a document to start.", 
            anchor="w",
            font=ctk.CTkFont(slant="italic")
        )
        self.status_label.grid(row=0, column=0, padx=5, pady=(0, 10), sticky="ew")
        
        # Tab View
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=1, column=0, sticky="nsew")
        
        self.tab_editor = self.tabview.add("Text Editor")
        self.tab_summary = self.tabview.add("Summary View")
        self.tab_quiz = self.tabview.add("Quiz Board")
        
        # Setup Text Editor Tab
        self.tab_editor.grid_columnconfigure(0, weight=1)
        self.tab_editor.grid_rowconfigure(0, weight=1)
        self.textbox_editor = ctk.CTkTextbox(self.tab_editor, font=("Consolas", 12))
        self.textbox_editor.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Setup Summary Tab
        self.tab_summary.grid_columnconfigure(0, weight=1)
        self.tab_summary.grid_rowconfigure(0, weight=1)
        self.textbox_summary = ctk.CTkTextbox(self.tab_summary, font=("Segoe UI", 12))
        self.textbox_summary.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Setup Quiz Tab
        self.tab_quiz.grid_columnconfigure(0, weight=1)
        self.tab_quiz.grid_rowconfigure(0, weight=1)
        self.textbox_quiz = ctk.CTkTextbox(self.tab_quiz, font=("Segoe UI", 12))
        self.textbox_quiz.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Bottom Status Bar / Path viewer
        self.path_label = ctk.CTkLabel(
            self.main_frame, 
            text="No file loaded", 
            anchor="w", 
            text_color="gray50",
            font=ctk.CTkFont(size=11)
        )
        self.path_label.grid(row=2, column=0, padx=5, pady=(10, 0), sticky="ew")
        
    def open_github(self):
        import webbrowser
        webbrowser.open("https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant")

    def toggle_mode(self, mode):
        self.api_mode = mode.lower()
        if self.api_mode == "online":
            # Repack controls inside inner settings container to keep them in order
            self.len_label.pack_forget()
            self.min_slider.pack_forget()
            self.max_slider.pack_forget()
            
            self.api_key_entry.pack(fill="x", pady=(5, 8))
            self.len_label.pack(anchor="w", pady=(4, 2))
            self.min_slider.pack(fill="x", pady=4)
            self.max_slider.pack(fill="x", pady=4)
        else:
            self.api_key_entry.pack_forget()
            
    def update_slider_label(self, val):
        min_v = int(self.min_slider.get())
        max_v = int(self.max_slider.get())
        if min_v >= max_v:
            max_v = min_v + 20
            self.max_slider.set(max_v)
        self.len_label.configure(text=f"Min/Max length: {min_v} / {max_v}")
        
    def change_appearance(self, mode):
        ctk.set_appearance_mode(mode.lower())
        
    def load_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a file",
            filetypes=[
                ("All Supported", "*.pdf *.txt *.png *.jpg *.jpeg"),
                ("PDF files", "*.pdf"),
                ("Text files", "*.txt"),
                ("Image files", "*.png *.jpg *.jpeg")
            ]
        )
        if not file_path:
            return

        self.file_path = file_path
        self.path_label.configure(text=f"Loaded: {os.path.basename(file_path)}")
        self.status_label.configure(text="Extracting text layers...")
        self.update()
        
        try:
            self.text_data = load_text_from_file(file_path)
            self.textbox_editor.delete("1.0", "end")
            self.textbox_editor.insert("1.0", self.text_data)
            
            # Switch to Text Editor Tab automatically
            self.tabview.set("Text Editor")
            self.status_label.configure(text="✅ File loaded successfully.")
            messagebox.showinfo("✅ Success", "File loaded successfully!")
        except Exception as e:
            self.status_label.configure(text="❌ Failed to load file.")
            messagebox.showerror("❌ Error", f"Failed to load file: {str(e)}")

    def do_summary(self):
        # Read edited content from editor textbox if user made tweaks
        editor_text = self.textbox_editor.get("1.0", "end-1c").strip()
        if not editor_text:
            messagebox.showwarning("⚠️ Empty Editor", "Please load a file or write some text in the Editor first.")
            return

        self.status_label.configure(text="⏳ Generating summary (running model)...")
        self.update()
        
        try:
            api_key = self.api_key_entry.get().strip() if self.api_mode == "online" else ""
            config = {"mode": self.api_mode, "api_key": api_key}
            
            min_v = int(self.min_slider.get())
            max_v = int(self.max_slider.get())
            
            self.summary_data = summarize_text(editor_text, min_v, max_v, config)
            self.textbox_summary.delete("1.0", "end")
            self.textbox_summary.insert("1.0", self.summary_data)
            
            # Switch to Summary View Tab automatically
            self.tabview.set("Summary View")
            self.status_label.configure(text="✅ Summary generated.")
            messagebox.showinfo("✅ Done", "Summary generated!")
        except Exception as e:
            self.status_label.configure(text="❌ Failed to generate summary.")
            messagebox.showerror("❌ Error", f"Failed to generate summary: {str(e)}")

    def do_ocr(self):
        if not self.file_path:
            messagebox.showwarning("⚠️ No file", "Please choose an image file first.")
            return
        
        self.status_label.configure(text="⏳ Running OpenCV & Tesseract OCR...")
        self.update()
        
        try:
            ocr_text = extract_text_from_image(self.file_path)
            if not ocr_text.strip():
                self.status_label.configure(text="⚠️ OCR found no readable text.")
                messagebox.showwarning("⚠️ No text", "No text found in the image.")
                return

            self.text_data = ocr_text
            self.textbox_editor.delete("1.0", "end")
            self.textbox_editor.insert("1.0", ocr_text)
            
            # Switch to Text Editor Tab automatically
            self.tabview.set("Text Editor")
            self.status_label.configure(text="✅ OCR completed successfully.")
            messagebox.showinfo("✅ Done", "OCR completed!")
        except Exception as e:
            self.status_label.configure(text="❌ OCR processing failed.")
            messagebox.showerror("❌ Error", f"OCR failed: {str(e)}")

    def do_quiz(self):
        # We need a summary to generate questions from
        summary_text = self.textbox_summary.get("1.0", "end-1c").strip()
        if not summary_text:
            # If no summary, try using editor text directly
            editor_text = self.textbox_editor.get("1.0", "end-1c").strip()
            if not editor_text:
                messagebox.showwarning("⚠️ No Content", "Generate a summary or type text first to generate a quiz.")
                return
            summary_text = editor_text
            
        self.status_label.configure(text="⏳ Extracting NLTK keywords and generating quiz...")
        self.update()
        
        try:
            self.questions = generate_questions(summary_text, num_questions=5)
            if not self.questions:
                self.status_label.configure(text="⚠️ Failed to generate quiz questions.")
                messagebox.showwarning("⚠️ Quiz Error", "Could not extract enough sentences/keywords to generate quiz questions.")
                return
                
            self.textbox_quiz.delete("1.0", "end")
            
            # Render formatted questions in Quiz Tab
            quiz_text = ""
            for i, q in enumerate(self.questions, 1):
                quiz_text += f"Question {i}: {q['question']}\n"
                for j, opt in enumerate(q['options'], 1):
                    quiz_text += f"   {chr(64+j)}. {opt}\n"
                quiz_text += f"👉 Correct Answer: {q['answer']}\n\n"
                quiz_text += "-" * 50 + "\n\n"
                
            self.textbox_quiz.insert("1.0", quiz_text)
            self.tabview.set("Quiz Board")
            self.status_label.configure(text="✅ Quiz generated successfully.")
            messagebox.showinfo("✅ Success", "Quiz generated successfully!")
        except Exception as e:
            self.status_label.configure(text="❌ Quiz generation failed.")
            messagebox.showerror("❌ Error", f"Failed to generate quiz: {str(e)}")

    def export_pdf(self):
        # Prompt user to choose what to export
        active_tab = self.tabview.get()
        theme = self.appearance_switch.get().lower()
        
        if active_tab == "Summary View":
            summary_text = self.textbox_summary.get("1.0", "end-1c").strip()
            if not summary_text:
                messagebox.showwarning("⚠️ Empty Summary", "No summary content to export.")
                return
            try:
                self.status_label.configure(text="⏳ Generating Summary PDF...")
                self.update()
                pdf_path = export_summary_to_pdf(summary_text, theme=theme)
                self.status_label.configure(text="✅ Summary PDF saved.")
                messagebox.showinfo("✅ Done", f"Saved Summary PDF to:\n{pdf_path}")
            except Exception as e:
                self.status_label.configure(text="❌ Export failed.")
                messagebox.showerror("Error", f"Failed to export PDF: {str(e)}")
                
        elif active_tab == "Quiz Board":
            if not self.questions:
                messagebox.showwarning("⚠️ Empty Quiz", "No quiz questions generated to export.")
                return
            try:
                self.status_label.configure(text="⏳ Generating Quiz PDF...")
                self.update()
                pdf_path = export_quiz_to_pdf(self.questions, theme=theme)
                self.status_label.configure(text="✅ Quiz PDF saved.")
                messagebox.showinfo("✅ Done", f"Saved Quiz PDF to:\n{pdf_path}")
            except Exception as e:
                self.status_label.configure(text="❌ Export failed.")
                messagebox.showerror("Error", f"Failed to export PDF: {str(e)}")
                
        else:
            # Offer general export options
            choice = messagebox.askyesnocancel(
                "Export PDF", 
                "Do you want to export the Summary? (Click Yes)\nOr export the Quiz? (Click No)"
            )
            if choice is True: # Export Summary
                summary_text = self.textbox_summary.get("1.0", "end-1c").strip()
                if not summary_text:
                    messagebox.showwarning("⚠️ Empty Summary", "Please generate a summary first.")
                    return
                try:
                    pdf_path = export_summary_to_pdf(summary_text, theme=theme)
                    messagebox.showinfo("✅ Done", f"Saved Summary PDF to:\n{pdf_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export PDF: {str(e)}")
            elif choice is False: # Export Quiz
                if not self.questions:
                    messagebox.showwarning("⚠️ Empty Quiz", "Please generate a quiz first.")
                    return
                try:
                    pdf_path = export_quiz_to_pdf(self.questions, theme=theme)
                    messagebox.showinfo("✅ Done", f"Saved Quiz PDF to:\n{pdf_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export PDF: {str(e)}")

if __name__ == "__main__":
    app = StudySageApp()
    app.mainloop()