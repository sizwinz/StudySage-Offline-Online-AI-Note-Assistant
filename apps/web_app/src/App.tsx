import React, { useState, useRef, useEffect } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000';

interface Question {
  question: string;
  options: string[];
  answer: string;
}

interface AnswerState {
  selectedOption: string;
  isCorrect: boolean;
}

export default function App() {
  // App States
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');
  const [processingMode, setProcessingMode] = useState<'offline' | 'online'>('offline');
  const [apiKey, setApiKey] = useState('');
  const [minLength, setMinLength] = useState(30);
  const [maxLength, setMaxLength] = useState(150);
  
  const [file, setFile] = useState<File | null>(null);
  const [editorText, setEditorText] = useState('');
  const [summaryText, setSummaryText] = useState('');
  const [questions, setQuestions] = useState<Question[]>([]);
  const [activeTab, setActiveTab] = useState<'editor' | 'summary' | 'quiz'>('editor');
  
  // Status and Loaders
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [statusMsg, setStatusMsg] = useState('Ready. Load a document to start.');
  
  // Interactive Quiz States
  const [answers, setAnswers] = useState<Record<number, AnswerState>>({});
  const [quizScore, setQuizScore] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync theme attribute to HTML tag
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Handle Drag & Drop Events
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      processUploadedFile(droppedFile);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processUploadedFile(e.target.files[0]);
    }
  };

  const processUploadedFile = async (selectedFile: File) => {
    setFile(selectedFile);
    setIsLoading(true);
    setLoadingMsg('Extracting text (running OCR/native parser)...');
    setStatusMsg(`Uploading ${selectedFile.name}...`);
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('lang', 'auto');
    
    try {
      const res = await fetch(`${API_BASE}/api/ocr`, {
        method: 'POST',
        body: formData,
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to parse file.');
      }
      
      const data = await res.json();
      setEditorText(data.text || '');
      setSummaryText('');
      setQuestions([]);
      setAnswers({});
      setQuizScore(0);
      setActiveTab('editor');
      setStatusMsg(`✅ Text extracted from ${selectedFile.name} successfully.`);
    } catch (e: any) {
      console.error(e);
      setStatusMsg(`❌ Error: ${e.message}`);
      alert(`Error loading file: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const removeFile = () => {
    setFile(null);
    setEditorText('');
    setSummaryText('');
    setQuestions([]);
    setAnswers({});
    setQuizScore(0);
    setActiveTab('editor');
    setStatusMsg('File cleared. Load a new file to start.');
  };

  // Run Summary Engine
  const handleGenerateSummary = async () => {
    if (!editorText.trim()) {
      alert('Please load a file or write some text in the Editor first.');
      return;
    }
    
    setIsLoading(true);
    setLoadingMsg('Generating summary (processing model)...');
    setStatusMsg('Running summarization model...');
    
    try {
      const res = await fetch(`${API_BASE}/api/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: editorText,
          mode: processingMode,
          api_key: processingMode === 'online' ? apiKey : '',
          min_length: minLength,
          max_length: maxLength
        }),
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Summarization failed.');
      }
      
      const data = await res.json();
      setSummaryText(data.summary || '');
      setActiveTab('summary');
      setStatusMsg('✅ Summary generated successfully.');
    } catch (e: any) {
      console.error(e);
      setStatusMsg(`❌ Summary failed: ${e.message}`);
      alert(`Summarization Error: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Run Quiz Generator
  const handleGenerateQuiz = async (numQ: number = 5) => {
    const textForQuiz = summaryText.trim() || editorText.trim();
    if (!textForQuiz) {
      alert('Please load text or generate a summary first to create a quiz.');
      return;
    }
    
    setIsLoading(true);
    setLoadingMsg('Extracting keywords & compiling quiz questions...');
    setStatusMsg('Generating quiz cards...');
    
    try {
      const res = await fetch(`${API_BASE}/api/quiz`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: textForQuiz,
          num_questions: numQ
        }),
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Quiz generation failed.');
      }
      
      const data = await res.json();
      setQuestions(data.questions || []);
      setAnswers({});
      setQuizScore(0);
      setActiveTab('quiz');
      setStatusMsg('✅ Interactive quiz ready.');
    } catch (e: any) {
      console.error(e);
      setStatusMsg(`❌ Quiz generation failed: ${e.message}`);
      alert(`Quiz Error: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Interactive Quiz Option Selection
  const selectOption = (qIdx: number, option: string, correctAns: string) => {
    if (answers[qIdx]) return; // Already answered
    
    const isCorrect = option.toLowerCase() === correctAns.toLowerCase();
    setAnswers(prev => ({
      ...prev,
      [qIdx]: { selectedOption: option, isCorrect }
    }));
    
    if (isCorrect) {
      setQuizScore(prev => prev + 1);
    }
  };

  const resetQuiz = () => {
    setAnswers({});
    setQuizScore(0);
  };

  // PDF Export Handlers
  const exportPDF = async (type: 'summary' | 'quiz') => {
    if (type === 'summary' && !summaryText) {
      alert('No summary content to export.');
      return;
    }
    if (type === 'quiz' && questions.length === 0) {
      alert('No quiz questions generated to export.');
      return;
    }
    
    setIsLoading(true);
    setLoadingMsg('Generating PDF stream (applying theme elements)...');
    setStatusMsg(`Exporting ${type} PDF...`);
    
    try {
      const endpoint = type === 'summary' ? '/api/export-summary' : '/api/export-quiz';
      const bodyPayload = type === 'summary' 
        ? { summary: summaryText, theme }
        : { questions, theme };
        
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload),
      });
      
      if (!res.ok) {
        throw new Error('Failed to generate export stream.');
      }
      
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `studysage_${type}_${theme}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      
      setStatusMsg(`✅ ${type} PDF exported successfully.`);
    } catch (e: any) {
      console.error(e);
      setStatusMsg(`❌ PDF Export failed: ${e.message}`);
      alert(`Export Error: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleMinSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value);
    setMinLength(val);
    if (val >= maxLength) {
      setMaxLength(val + 20);
    }
  };

  const handleMaxSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value);
    setMaxLength(val);
    if (val <= minLength) {
      setMinLength(Math.max(10, val - 20));
    }
  };

  return (
    <div className="app-container">
      {/* 1. SIDEBAR CONFIGURATION PANEL */}
      <aside className="sidebar">
        <div className="brand">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <img src="/logo.png" alt="Logo" style={{ width: '40px', height: '40px', objectFit: 'contain' }} />
            <div>
              <div className="brand-name">StudySage</div>
              <div className="brand-subtitle">Offline / Online AI Assistant</div>
            </div>
          </div>
          <a 
            href="https://github.com/sizwinz/StudySage-Offline-Online-AI-Note-Assistant" 
            target="_blank" 
            rel="noopener noreferrer"
            style={{ 
              fontSize: '12px', 
              color: 'var(--text-secondary)', 
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              marginTop: '4px',
              transition: 'color 0.2s'
            }}
            onMouseOver={(e) => e.currentTarget.style.color = 'var(--accent-blue)'}
            onMouseOut={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
          >
            📁 GitHub Repository
          </a>
        </div>
        
        <div className="settings-section">
          <div className="section-title">Settings</div>
          
          <div className="control-group">
            <span className="control-label">Processing Mode</span>
            <div className="segmented-control">
              <button 
                className={`segmented-btn ${processingMode === 'offline' ? 'active' : ''}`}
                onClick={() => setProcessingMode('offline')}
              >
                Offline
              </button>
              <button 
                className={`segmented-btn ${processingMode === 'online' ? 'active' : ''}`}
                onClick={() => setProcessingMode('online')}
              >
                Online
              </button>
            </div>
          </div>
          
          {processingMode === 'online' && (
            <div className="control-group">
              <label className="control-label" htmlFor="api-key-input">Hugging Face API Key</label>
              <input
                id="api-key-input"
                type="password"
                className="text-input"
                placeholder="Enter HF API token..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
          )}
          
          <div className="control-group">
            <div className="slider-group">
              <div className="slider-values">
                <span>Min Length</span>
                <span>{minLength} words</span>
              </div>
              <input 
                type="range"
                className="range-slider"
                min="10"
                max="100"
                value={minLength}
                onChange={handleMinSliderChange}
                aria-label="Minimum summary length"
              />
            </div>
          </div>
          
          <div className="control-group">
            <div className="slider-group">
              <div className="slider-values">
                <span>Max Length</span>
                <span>{maxLength} words</span>
              </div>
              <input 
                type="range"
                className="range-slider"
                min="50"
                max="500"
                value={maxLength}
                onChange={handleMaxSliderChange}
                aria-label="Maximum summary length"
              />
            </div>
          </div>
        </div>
        
        <div className="settings-section">
          <div className="section-title">Core Actions</div>
          <div className="action-buttons">
            <button className="primary-btn" onClick={handleGenerateSummary}>
              🧠 Generate Summary
            </button>
            <button className="secondary-btn" onClick={() => handleGenerateQuiz(5)}>
              🧪 Generate Quiz
            </button>
          </div>
        </div>
        
        <div className="bottom-controls">
          <span className="control-label">Theme</span>
          <div className="segmented-control" style={{ width: '130px' }}>
            <button 
              className={`segmented-btn ${theme === 'light' ? 'active' : ''}`}
              onClick={() => setTheme('light')}
            >
              Light
            </button>
            <button 
              className={`segmented-btn ${theme === 'dark' ? 'active' : ''}`}
              onClick={() => setTheme('dark')}
            >
              Dark
            </button>
          </div>
        </div>
      </aside>
      
      {/* 2. MAIN WORKSPACE AREA */}
      <main className="main-content">
        {isLoading && (
          <div className="spinner-container">
            <div className="spinner"></div>
            <p style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{loadingMsg}</p>
          </div>
        )}
        
        <div className="status-banner">
          <span>🎯 Status: {statusMsg}</span>
        </div>
        
        {/* Upload zone if no file is present */}
        {!file && (
          <div 
            className="dropzone"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input 
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              style={{ display: 'none' }}
              accept=".pdf,.txt,.png,.jpg,.jpeg"
            />
            <div className="dropzone-icon">📂</div>
            <div className="dropzone-text">Drag & drop your files here</div>
            <div className="dropzone-hint">Supports PDF, TXT, PNG, JPG (Max 20MB)</div>
          </div>
        )}
        
        {file && (
          <div className="file-info">
            <span>📄 File: <strong>{file.name}</strong> ({(file.size / 1024 / 1024).toFixed(2)} MB)</span>
            <button className="file-remove" onClick={removeFile}>Remove File</button>
          </div>
        )}
        
        {/* Tabs display */}
        <div className="tabs-container">
          <div className="tab-headers">
            <button 
              className={`tab-header ${activeTab === 'editor' ? 'active' : ''}`}
              onClick={() => setActiveTab('editor')}
            >
              Text Editor
            </button>
            <button 
              className={`tab-header ${activeTab === 'summary' ? 'active' : ''}`}
              onClick={() => setActiveTab('summary')}
            >
              Summary View
            </button>
            <button 
              className={`tab-header ${activeTab === 'quiz' ? 'active' : ''}`}
              onClick={() => setActiveTab('quiz')}
            >
              Quiz Board
            </button>
          </div>
          
          <div className="tab-content">
            {activeTab === 'editor' && (
              <textarea
                className="editor-textbox"
                placeholder="Text layer or OCR extraction output will appear here. You can also write or edit text directly..."
                value={editorText}
                onChange={(e) => setEditorText(e.target.value)}
                aria-label="Document editor textbox"
              />
            )}
            
            {activeTab === 'summary' && (
              <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                <textarea
                  className="editor-textbox"
                  value={summaryText}
                  onChange={(e) => setSummaryText(e.target.value)}
                  placeholder="No summary generated yet. Click 'Generate Summary' in the sidebar to start."
                  aria-label="Summary text editor"
                />
                {summaryText && (
                  <div className="result-actions">
                    <button className="primary-btn" onClick={() => exportPDF('summary')}>
                      📄 Export Summary PDF
                    </button>
                  </div>
                )}
              </div>
            )}
            
            {activeTab === 'quiz' && (
              <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                {questions.length === 0 ? (
                  <div className="result-box" style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                    No quiz generated yet. Click 'Generate Quiz' in the sidebar to create one.
                  </div>
                ) : (
                  <>
                    <div className="quiz-header">
                      <span className="quiz-score">Score: {quizScore} / {questions.length}</span>
                      <button className="secondary-btn" onClick={resetQuiz}>Reset Score</button>
                    </div>
                    
                    <div className="quiz-list">
                      {questions.map((q, qIdx) => (
                        <div className="quiz-card" key={qIdx}>
                          <div className="quiz-question">{qIdx + 1}. {q.question}</div>
                          <div className="quiz-options">
                            {q.options.map((opt, oIdx) => {
                              const ansState = answers[qIdx];
                              let classes = '';
                              if (ansState) {
                                classes += ' disabled';
                                if (opt === q.answer) {
                                  classes += ' correct'; // Always highlight correct answer green
                                } else if (ansState.selectedOption === opt && !ansState.isCorrect) {
                                  classes += ' incorrect'; // Highlight wrong selection red
                                }
                              }
                              return (
                                <button
                                  key={oIdx}
                                  className={`quiz-option-btn${classes}`}
                                  onClick={() => selectOption(qIdx, opt, q.answer)}
                                  disabled={!!ansState}
                                >
                                  {chrLetter(oIdx)}. {opt}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    <div className="result-actions">
                      <button className="primary-btn" onClick={() => exportPDF('quiz')}>
                        📄 Export Quiz PDF
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// Option Letter helper
function chrLetter(idx: number) {
  return String.fromCharCode(65 + idx);
}
