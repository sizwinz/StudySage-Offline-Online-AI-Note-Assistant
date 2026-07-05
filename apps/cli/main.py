import sys
from pathlib import Path

# Ensure repo root is on sys.path before core imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import os
import platform
from pathlib import Path
from core.summarize import summarize_text, get_model_path
from core.quiz_gen import generate_questions
from core.export_pdf import export_summary_to_pdf, export_quiz_to_pdf
from core.ocr_reader import extract_text_from_image
from core.io import load_text_from_file
from pyfiglet import Figlet
from colorama import Fore, Style, init
from datetime import datetime
import requests
import json
import torch
import logging

# Import configuration from the new config module
try:
    from config import (
        ONLINE_MODE_MAX_CHARS, ONLINE_MODE_MAX_WORDS,
        OFFLINE_MODE_MAX_CHARS, OFFLINE_MODE_MAX_WORDS,
        OUTPUT_DIR
    )
except ImportError:
    # Fallback if config.py doesn't exist yet
    ONLINE_MODE_MAX_CHARS = 4000
    ONLINE_MODE_MAX_WORDS = 800
    OFFLINE_MODE_MAX_CHARS = 100000
    OFFLINE_MODE_MAX_WORDS = 20000
    OUTPUT_DIR = "output"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)
MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)

init(autoreset=True)

CONFIG_FILE = Path("config.json")

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"mode": "offline", "api_key": ""}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def clear_terminal():
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')

def print_logo():
    clear_terminal()
    f = Figlet(font='slant')
    print(Fore.CYAN + f.renderText("StudySage"))
    print(Fore.YELLOW + "StudySage – AI Note Assistant by Sahaj33")
    print(Fore.BLUE + "🌐 GitHub: https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant\n")

def print_mode_banner(mode):
    clear_terminal()
    f = Figlet(font='slant')
    print(Fore.CYAN + f.renderText("StudySage"))
    mode_text = "OFFLINE MODE" if mode == "offline" else "ONLINE MODE"
    mode_color = Fore.GREEN if mode == "offline" else Fore.BLUE
    print(mode_color + "=" * 50)
    print(mode_color + f"🎯 {mode_text} ACTIVATED")
    print(mode_color + "=" * 50 + "\n")
    print(Fore.YELLOW + "StudySage – AI Note Assistant by Sahaj33")
    print(Fore.BLUE + "🌐 GitHub: https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant\n")


def count_words(text):
    return len(text.split())

def count_chars(text):
    return len(text)

def check_text_limits(text, mode):
    words = count_words(text)
    chars = count_chars(text)
    
    if mode == "online":
        if words > ONLINE_MODE_MAX_WORDS or chars > ONLINE_MODE_MAX_CHARS:
            return False, f"Text exceeds online mode limits (max {ONLINE_MODE_MAX_WORDS} words or {ONLINE_MODE_MAX_CHARS} chars)."
    else:
        if words > OFFLINE_MODE_MAX_WORDS or chars > OFFLINE_MODE_MAX_CHARS:
            return False, f"Text exceeds offline mode limits (max {OFFLINE_MODE_MAX_WORDS} words or {OFFLINE_MODE_MAX_CHARS} chars)."
    
    return True, ""

def display_results(summary, questions=None):
    clear_terminal()
    print(Fore.GREEN + "\n📝 Summary:")
    print(Fore.WHITE + summary + "\n")
    
    if questions:
        print(Fore.GREEN + "📝 Quiz Questions:")
        for i, q in enumerate(questions, 1):
            print(Fore.CYAN + f"\nQuestion {i}: {q['question']}")
            print(Fore.YELLOW + "Options:")
            for j, option in enumerate(q["options"], 1):
                print(f"{j}. {option}")
            print(Fore.GREEN + f"Correct Answer: {q['answer']}")

def run_features(choice, text, min_len, max_len, config, last_summary=None):
    summary = last_summary
    questions = None
    
    if choice == "1":  # Summary
        summary = summarize_text(text, min_len, max_len, config)
        display_results(summary)
        
        save_pdf = input(Fore.CYAN + "\n💾 Save summary as PDF? (y/n): ").strip().lower()
        if save_pdf == 'y':
            pdf_path = export_summary_to_pdf(summary)
            print(Fore.GREEN + "✅ Summary PDF saved.")
        
        return summary, None
    
    elif choice == "2":  # Quiz
        if not summary:
            summary = summarize_text(text, min_len, max_len, config)
        num_questions = input(Fore.YELLOW + "Enter number of questions (1-20): ")
        try:
            num_questions = max(1, min(20, int(num_questions)))
        except ValueError:
            num_questions = 5  # Default
            print(Fore.YELLOW + "Invalid input. Using 5 questions.")
        
        print(Fore.BLUE + "[+] Generating quiz...")
        questions = generate_questions(summary, num_questions)
        display_results(summary, questions)
        
        save_pdf = input(Fore.CYAN + "\n💾 Save quiz as PDF? (y/n): ").strip().lower()
        if save_pdf == 'y':
            pdf_path = export_quiz_to_pdf(questions)
            print(Fore.GREEN + "✅ Quiz PDF saved.")
        
        return summary, questions

def setup_mode():
    config = load_config()
    
    while True:
        print(Fore.YELLOW + "\nSelect processing mode:")
        print("1. Offline (slower, no API key)")
        print("2. Online (faster, requires API key)")
        print("3. Exit")
        
        choice = input(Fore.CYAN + "\nEnter choice (1-3): ")
        
        if choice == "1":
            config["mode"] = "offline"
            save_config(config)
            print_mode_banner("offline")
            return config
        
        elif choice == "2":
            api_key = input(Fore.YELLOW + "Enter Hugging Face API key: ").strip()
            if not api_key:
                print(Fore.RED + "❌ API key required for online mode.")
                continue
            
            config["mode"] = "online"
            config["api_key"] = api_key
            save_config(config)
            print_mode_banner("online")
            return config
        
        elif choice == "3":
            print(Fore.YELLOW + "Goodbye!")
            sys.exit(0)
        
        else:
            print(Fore.RED + "❌ Invalid choice.")

def process_file(file_path, mode="online", api_key=None, min_length=30, max_length=200, lang='eng'):
    config = {"mode": mode, "api_key": api_key or ""}
    text = load_text_from_file(file_path, lang=lang)
    if not text:
        return "No text could be extracted from the file. The file may be empty, contain no recognizable text, or OCR may have failed."
    summary = summarize_text(text, min_length, max_length, config)
    return summary

def main():
    print_logo()
    config = setup_mode()
    
    last_file_path = None
    last_text = None
    last_summary = None
    last_questions = None
    
    while True:
        print(Fore.YELLOW + "\n📝 Customize Summary Length:")
        length_input = input("Enter min,max (or press Enter for default [30,200]) or type 0 to exit: ")
        
        if length_input == "0":
            print(Fore.YELLOW + "Goodbye!")
            break
        
        try:
            if length_input:
                min_len, max_len = map(int, length_input.split(','))
            else:
                min_len, max_len = 30, 200
        except ValueError:
            print(Fore.RED + "❌ Invalid input. Using default values.")
            min_len, max_len = 30, 200
        
        if not last_file_path:
            print(Fore.YELLOW + "\n📂 Enter note file path (.txt, .md, .pdf, .png/.jpg): ")
            file_path = input().strip()
            
            if not file_path:
                print(Fore.RED + "❌ No file path provided.")
                continue
            
            try:
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    print(Fore.BLUE + "\n🌐 Available OCR languages: https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html")
                    print(Fore.YELLOW + "\n🌐 NOTE: Use high-quality images for best results.")
                    lang = input(Fore.BLUE + "\n🌐 Enter OCR language code (Enter for 'eng'): ").strip() or 'eng'
                    text = load_text_from_file(file_path, lang)
                else:
                    text = load_text_from_file(file_path)
                
                last_file_path = file_path
                last_text = text
                last_summary = None
                last_questions = None
            except Exception as e:
                print(Fore.RED + f"\n❌ Error: {str(e)}")
                input(Fore.YELLOW + "\nPress Enter to continue...")
                continue
        
        print(Fore.YELLOW + "\nSelect feature:")
        print("1. Generate Summary")
        print("2. Generate Quiz")
        print("3. Change File")
        print("4. Back to Mode Selection")
        
        feature_choice = input(Fore.CYAN + "\nEnter choice (1-4): ")
        
        try:
            if feature_choice == "1":
                result = run_features("1", last_text, min_len, max_len, config)
                last_summary, last_questions = result if result else (None, None)
                quiz_choice = input(Fore.CYAN + "\nGenerate quiz questions? (y/n): ").strip().lower()
                if quiz_choice == 'y':
                    result = run_features("2", last_text, min_len, max_len, config, last_summary)
                    last_summary, last_questions = result if result else (None, None)
            
            elif feature_choice == "2":
                result = run_features("2", last_text, min_len, max_len, config, last_summary)
                last_summary, last_questions = result if result else (None, None)
            
            elif feature_choice == "3":
                last_file_path = None
                last_text = None
                last_summary = None
                last_questions = None
                continue
            
            elif feature_choice == "4":
                config = setup_mode()
                last_file_path = None
                last_text = None
                last_summary = None
                last_questions = None
                continue
            
            else:
                print(Fore.RED + "❌ Invalid choice.")
            
            input(Fore.GREEN + "\n✅ Press Enter to continue...")
        
        except Exception as e:
            print(Fore.RED + f"\n❌ Error: {str(e)}")
            input(Fore.YELLOW + "\nPress Enter to continue...")

if __name__ == "__main__":
    main()