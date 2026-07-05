import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import streamlit as st
import os
from pathlib import Path

# Import configuration
try:
    from config import OUTPUT_DIR
except ImportError:
    OUTPUT_DIR = "output"

from core.io import load_text_from_file, process_file
from core.quiz_gen import generate_questions
from core.export_pdf import export_summary_to_pdf, export_quiz_to_pdf

# Set page config
st.set_page_config(
    page_title="StudySage AI Note Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'summary' not in st.session_state:
    st.session_state.summary = ""
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'file_processed' not in st.session_state:
    st.session_state.file_processed = False

# Create output directory
OUTPUT_PATH = Path(OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)

# Helper function to dynamically swap colors and assets based on the active theme
def get_theme_colors():
    # Light theme color palette
    return {
        "background": "#ffffff",
        "secondary_background": "#f4f4f5",
        "sidebar_background": "#fafafa",
        "sidebar_border": "#e4e4e7",
        "border": "#e4e4e7",
        "text": "#18181b",
        "text_muted": "#71717a",
        "primary_button_bg": "#18181b",
        "primary_button_text": "#ffffff",
        "title_gradient_start": "#18181b",
        "title_gradient_end": "#71717a",
    }

colors = get_theme_colors()

# Inject Modern CSS that adapts dynamically to light & dark themes
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;700;800&display=swap');

/* Global Font Override */
html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

h1, h2, h3, h4, h5, h6 {{
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
}}

/* Dynamic theme adaptations */
[data-testid="stAppViewContainer"] {{
    background-color: {colors['background']};
    color: {colors['text']};
}}

/* Sidebar Custom styling */
[data-testid="stSidebar"] {{
    background-color: {colors['sidebar_background']} !important;
    border-right: 1px solid {colors['sidebar_border']};
}}

/* Cards & Text Area Custom Styles */
.stTextArea textarea {{
    background-color: {colors['secondary_background']} !important;
    border: 1px solid {colors['border']} !important;
    color: {colors['text']} !important;
    border-radius: 10px !important;
    font-size: 14px;
}}
.stTextArea textarea:focus {{
    border-color: {colors['primary_button_bg']} !important;
    box-shadow: 0 0 0 1px {colors['primary_button_bg']} !important;
}}

/* Inputs & Widgets styling */
div[data-baseweb="input"] {{
    background-color: {colors['secondary_background']} !important;
    border-radius: 8px !important;
}}
input {{
    color: {colors['text']} !important;
}}

/* Segmented Control & Radios */
div[data-testid="stRadio"] label {{
    font-size: 13px !important;
    color: {colors['text_muted']} !important;
}}

/* Custom premium card design for results */
.result-card {{
    background-color: {colors['secondary_background']};
    border: 1px solid {colors['border']};
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 20px;
}}

/* Beautiful Gradient Title */
.main-title {{
    background: linear-gradient(135deg, {colors['title_gradient_start']} 30%, {colors['title_gradient_end']} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.5rem;
    font-weight: 800;
    margin-bottom: 0px;
}}
.sub-title {{
    color: {colors['text_muted']};
    font-size: 0.95rem;
    margin-top: -10px;
    margin-bottom: 30px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}}

/* Modern minimalist buttons */
div.stButton > button {{
    background: {colors['secondary_background']} !important;
    color: {colors['text']} !important;
    border: 1px solid {colors['border']} !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    transition: all 0.2s ease-in-out !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
}}
div.stButton > button:hover {{
    background: {colors['background']} !important;
    border-color: {colors['primary_button_bg']} !important;
    color: {colors['primary_button_bg']} !important;
    transform: translateY(-1px);
}}
div.stButton > button:active {{
    transform: translateY(0px);
}}

/* Accent Process Button */
div.stButton > button[kind="primary"] {{
    background: {colors['primary_button_bg']} !important;
    color: {colors['primary_button_text']} !important;
    border: 1px solid {colors['primary_button_bg']} !important;
}}
div.stButton > button[kind="primary"]:hover {{
    background: {colors['primary_button_bg']} !important;
    opacity: 0.9;
    border-color: {colors['primary_button_bg']} !important;
    color: {colors['primary_button_text']} !important;
}}

/* Download buttons styling */
a[data-testid="stDownloadButton"] {{
    text-decoration: none !important;
    color: inherit !important;
}}

/* Sidebar links styling to prevent emoji underlines */
[data-testid="stSidebar"] a {{
    text-decoration: none !important;
}}
[data-testid="stSidebar"] a:hover {{
    text-decoration: underline !important;
}}
</style>
""", unsafe_allow_html=True)

# Helper function to load the light-theme logo (logo-black.png)
def get_theme_logo():
    logo_path = ROOT / "assets" / "images" / "logo-black.png"
    if not logo_path.exists():
        return str(ROOT / "assets" / "images" / "logo.png")
    return str(logo_path)

# Main Title Area
col_logo, col_header = st.columns([1, 6])
with col_logo:
    logo_path = get_theme_logo()
    if os.path.exists(logo_path):
        st.image(logo_path, width=80)
with col_header:
    st.markdown('<div class="main-title">StudySage AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Offline & Online Note Assistant</div>', unsafe_allow_html=True)

# ----------------- SIDEBAR CONFIGURATION -----------------
with st.sidebar:
    st.markdown("### Settings")
    
    # Mode selection
    mode = st.radio("Processing Mode", ["Offline (Private)", "Online (API-based)"], index=0)
    selected_mode = "offline" if mode == "Offline (Private)" else "online"
    
    # API Key input
    api_key_val = ""
    if selected_mode == "online":
        api_key_val = st.text_input("Hugging Face API Key", value=st.session_state.api_key or "", type="password")
        if api_key_val != st.session_state.api_key:
            st.session_state.api_key = api_key_val

    st.markdown("---")
    st.markdown("### Summary Length")
    min_length = st.slider("Min Length (words)", min_value=10, max_value=100, value=30)
    max_length = st.slider("Max Length (words)", min_value=50, max_value=500, value=150)
    
    st.markdown("---")
    st.markdown("### Export Customization")
    pdf_theme = st.selectbox("PDF Export Color Theme", ["Light Theme (Print)", "Dark Theme (Obsidian)"], index=0)
    selected_pdf_theme = "light" if pdf_theme == "Light Theme (Print)" else "dark"

    st.markdown("---")
    st.markdown("[📁 GitHub Repository](https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant)")


# ----------------- MAIN INTERFACE -----------------

# Document Upload
st.markdown("### Upload Document")
uploaded_file = st.file_uploader(
    "Choose a file (PDF, TXT, PNG, JPG, JPEG)", 
    type=['pdf', 'txt', 'png', 'jpg', 'jpeg'],
    label_visibility="collapsed"
)

if uploaded_file is not None:
    # Save file to central output directory
    file_path = os.path.join(OUTPUT_DIR, uploaded_file.name)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # Action buttons row
    col1, col2 = st.columns([1, 4])
    with col1:
        process_btn = st.button("Process Note", type="primary")
        
    if process_btn:
        try:
            with st.spinner("Analyzing document content..."):
                # Run core processing pipeline
                summary = process_file(
                    file_path, 
                    mode=selected_mode, 
                    api_key=st.session_state.api_key if selected_mode == "online" else "",
                    min_length=min_length,
                    max_length=max_length
                )
                
                st.session_state.summary = summary
                st.session_state.file_processed = True
                
                st.toast("Analysis complete!")
        except Exception as e:
            st.error(f"Error processing document: {str(e)}")
            
    # Display results
    if st.session_state.file_processed:
        st.markdown("---")
        st.markdown("### Results")
        
        tab_summary, tab_quiz = st.tabs(["Document Summary", "Interactive Quiz"])
        
        with tab_summary:
            st.markdown('<div class="result-card">', unsafe_allow_html=True)
            st.text_area("Summary Output", value=st.session_state.summary, height=250, label_visibility="collapsed")
            
            # Export controls
            st.markdown("#### Export summary")
            col_export_pdf, col_export_txt, _ = st.columns([1, 1, 3])
            
            with col_export_pdf:
                try:
                    pdf_path = export_summary_to_pdf(st.session_state.summary, theme=selected_pdf_theme)
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="Download Summary PDF",
                            data=f,
                            file_name=f"studysage_summary_{selected_pdf_theme}.pdf",
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"Error preparing PDF: {str(e)}")
                    
            with col_export_txt:
                st.download_button(
                    label="Download Summary Plain Text",
                    data=st.session_state.summary,
                    file_name="studysage_summary.txt",
                    mime="text/plain"
                )
            st.markdown('</div>', unsafe_allow_html=True)
            
        with tab_quiz:
            st.markdown('<div class="result-card">', unsafe_allow_html=True)
            col_slider, col_btn = st.columns([3, 1])
            with col_slider:
                num_questions = st.slider("Select number of questions", min_value=1, max_value=20, value=5)
            with col_btn:
                st.markdown("<div style='padding-top: 25px;'></div>", unsafe_allow_html=True)
                gen_quiz_btn = st.button("Generate Quiz")
                
            if gen_quiz_btn:
                try:
                    with st.spinner("Extracting terms and compiling options..."):
                        questions = generate_questions(st.session_state.summary, num_questions)
                        st.session_state.questions = questions
                        st.toast("Quiz generated successfully!")
                except Exception as e:
                    st.error(f"Error generating quiz: {str(e)}")
                    
            # Render Quiz Questions
            if st.session_state.questions:
                st.markdown("#### Test Your Understanding")
                for i, q in enumerate(st.session_state.questions, 1):
                    st.markdown(f"**Question {i}:** {q['question']}")
                    
                    # Interactive answer display using st.expander
                    options_str = ""
                    for j, opt in enumerate(q['options'], 1):
                        options_str += f"&nbsp;&nbsp;&nbsp;&nbsp;{chr(64+j)}. {opt}  \n"
                    st.markdown(options_str)
                    
                    with st.expander(f"Reveal Answer for Question {i}"):
                        st.success(f"Correct Answer: **{q['answer']}**")
                    st.markdown("---")
                
                # Quiz export
                st.markdown("#### Export quiz")
                try:
                    pdf_path = export_quiz_to_pdf(st.session_state.questions, theme=selected_pdf_theme)
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="Download Quiz PDF",
                            data=f,
                            file_name=f"studysage_quiz_{selected_pdf_theme}.pdf",
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"Error preparing quiz PDF: {str(e)}")
            st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("<br/><br/><hr/><center style='color: #71717a; font-size: 12px;'>StudySage AI - A minimal, high-fidelity note assistant.</center>", unsafe_allow_html=True)
