# MockTalk: Real-Time AI Group Discussion Simulator

![MockTalk Banner](https://via.placeholder.com/1200x500.png?text=MockTalk+AI+Dashboard+Screenshot)

**MockTalk** is an advanced, real-time AI-powered platform designed to help users prepare for Group Discussions (GD), commonly used in MBA admissions, campus placements, and corporate hiring. 

Instead of typing text to an AI, users **join a live voice-chat room** with multiple AI personas. The AI personas act as intelligent co-participants—they actively listen to the user, make their own arguments, interrupt, and react to the ongoing conversation in real-time. Once the session is over, the platform provides deep, actionable analytics on your performance using speech metrics and semantic analysis.

## 🚀 Key Features

- **Real-Time Voice Pipeline:** Ultra-low latency voice-in / voice-out pipeline seamlessly connecting the human user with AI personas over WebSockets.
- **Multiple AI Personas:** Practice with diverse AI personalities (e.g., The Leader, The Aggressor, The Analytical Thinker) driven by **Google Gemini**.
- **Dynamic Interruption & Turn-taking:** The AI doesn't just wait its turn. It listens to chunks of audio, determines when it's appropriate to interrupt, and simulates a genuine GD environment.
- **Post-GD Analytics Dashboard:** Get scored on leadership, logic, communication, and emotional intelligence. Review your actual audio transcripts mapped against the AI's evaluations.
- **Secure Authentication:** Firebase-powered authentication to save your session history and progress over time.

---

## 🏗️ System Architecture

The application is built on a modern, asynchronous tech stack divided into a Client-Side Single Page Application (SPA) and an Asynchronous AI Edge Server.

### 1. Frontend (Client)
- **Framework:** React 19 + TypeScript + Vite for ultra-fast builds.
- **Styling:** Vanilla CSS (Custom Design System) + Framer Motion for smooth, hardware-accelerated animations.
- **State Management:** Zustand for lightweight, boilerplate-free state keeping across the dashboard, audio visualizers, and room metadata.
- **Audio/VAD Interface:** `@ricky0123/vad-react` handles local microphone streaming and local Voice Activity Detection before sending raw chunks to the backend. 
- **Routing:** React Router v7.

### 2. Backend (Server)
- **Framework:** FastAPI running on Uvicorn (ASGI) to handle heavily concurrent WebSocket connections efficiently.
- **Real-Time Layer:** Native `websockets` library integrated deeply with FastAPI routers for bi-directional binary audio streaming and JSON metadata syncing.
- **AI Core (LLM):** **Google Gemini Flash 1.5** via `google-generativeai` SDK. LangGraph is used to orchestrate the state machine of the GD (who speaks next, what the context is).
- **Voice Pipeline (STT/TTS):**
  - **Speech-to-Text (STT):** Groq Whisper API (via HTTPX) for near-instant < 300ms transcription of user audio chunks.
  - **Text-to-Speech (TTS):** Edge TTS is utilized to generate human-sounding voices rapidly.
- **Authentication & DB:** Firebase Admin SDK securely verifies tokens sent from the frontend and manages user session data in Firestore.

---

## 🎙️ The Voice Pipeline & Latency Optimization

Achieving a "real" GD feel requires minimizing the "Walkie-Talkie" delay. Our target is a sub-800ms round-trip latency from the moment the user stops speaking to the moment the AI begins replying. 

**How we do it:**
1. **Continuous Chunking:** The frontend streams audio constantly. We do not wait for the user to click "stop" or hit an arbitrary time limit.
2. **Backend Consolidation:** We run Voice Activity Detection (VAD) algorithms. When silence is detected, the audio buffer is immediately flushed to **Groq Whisper** which transcribes it in ~200ms.
3. **Streaming LLM State:** The transcribed text is sent to the **LangGraph** orchestration edge. If LangGraph determines an AI should reply, it calls Gemini. We stream the tokens out of Gemini as they generate.
4. **Sentence-Boundary TTS:** Rather than waiting for the LLM to write a full paragraph, we chunk the streaming LLM text by sentence markers (`.`, `!`, `?`) and send them individually to the TTS engine. 
5. **WebSocket Playback:** The very first audio bytes of the TTS engine are pushed back down the WebSocket to the frontend, starting playback while the rest of the AI's sentence is still being written by the LLM in the cloud.

---

## 💻 Getting Started (Local Development)

### Prerequisites
- Node.js (v18+)
- Python (3.10+)
- Firebase Project Setup (Service Account Key)
- API Keys: 
  - `GEMINI_API_KEY`
  - `GROQ_API_KEY`

### 1. Clone & Environment Setup

```bash
git clone <your-repo-url>
cd gd-sim-ai
```

### 2. Backend Setup
```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```
Create a `.env` file in the `/backend` folder. Reference `.env.example`.
Drop your Firebase `serviceAccountKey.json` into the `/backend` folder.

Start the FastAPI server:
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
Open a new terminal window:
```bash
cd frontend
npm install
```
Create a `.env` file in the `/frontend` folder holding your Firebase client configuration (`VITE_FIREBASE_API_KEY`, etc.).

Start the Vite development server:
```bash
npm run dev
```

The application should now be running. Head to `localhost:5173` to sign in and start your first simulated group discussion!

---

## 🔮 Future Roadmap
- **Multiplayer "Real User" Rooms:** Adding WebRTC support (e.g., LiveKit or Daily.co) to allow up to 5 real humans to practice together while the AI acts as a silent observer/evaluator.
- **Video Analysis:** Integrating computer vision to track user body language, eye contact, and confidence during the simulation.
- **RAG for Custom Scenarios:** Injecting company-specific or industry-specific case studies via a vector database (ChromaDB). 

## 🛡️ License
MIT License.
