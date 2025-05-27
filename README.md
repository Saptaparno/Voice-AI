# Voice-Driven Agentic AI Chatbot

This is a beginner-friendly Python project that creates a voice-to-voice AI chatbot with advanced capabilities using LangChain and OpenAI:

- Converts user speech to text using Whisper ASR
- Uses OpenAI GPT for chatbot responses with conversation memory
- Performs sentiment analysis on user input
- Can search the web automatically when needed
- Responds with synthesized voice output
- Implements an agentic AI system that decides when to use tools like web search or sentiment analysis

---

## Features

- Voice input and output (microphone and speaker)
- Persistent conversation memory for context-aware replies
- Real-time sentiment analysis on user speech
- Intelligent decision-making for when to search the web
- Agent-driven tool selection using LangChain's agent framework

---

## Requirements

- Python 3.7+
- `langchain`
- `openai`
- `speechrecognition`
- `pyttsx3` (or other text-to-speech library)
- `pyaudio` (for microphone input)
- `requests` (for web search API)
- `python-dotenv`

---

## Setup

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install langchain openai speechrecognition pyttsx3 pyaudio requests python-dotenv
