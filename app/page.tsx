"use client";

import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Role = "user" | "assistant";
type Msg = { role: Role; text: string };

declare global {
  interface Window {
    webkitSpeechRecognition?: any;
    SpeechRecognition?: any;
  }
}

export default function Page() {
  const [cvText, setCvText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [applicationType, setApplicationType] = useState("Emploi");
  const [durationMinutes, setDurationMinutes] = useState(20);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [listening, setListening] = useState(false);
  const [status, setStatus] = useState("Prêt");
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [uploadingCv, setUploadingCv] = useState(false);
  const [cvFileName, setCvFileName] = useState("");

  // Camera state
  const [cameraActive, setCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Text input mode state
  const [textMode, setTextMode] = useState(false);
  const [textInput, setTextInput] = useState("");

  const recognitionRef = useRef<any>(null);
  const speakingRef = useRef(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const [speechSupported, setSpeechSupported] = useState(false);

  useEffect(() => {
    setSpeechSupported(
      typeof window !== "undefined" &&
      (!!window.SpeechRecognition || !!window.webkitSpeechRecognition)
    );
  }, []);

  const sendToGemini = async (finalReport = false, externalHistory?: Msg[]) => {
    const history = externalHistory ?? messages;
    setStatus(finalReport ? "Génération du compte rendu..." : "Le recruteur réfléchit...");

    const res = await fetch("/api/interview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cvText,
        jobTitle,
        jobDescription,
        applicationType,
        durationMinutes,
        history,
        finalReport,
      }),
    });

    const data = await res.json();
    const text = data?.text || data?.error || "Réponse vide.";
    setMessages((prev) => [...prev, { role: "assistant", text }]);
    speak(text);
    setStatus(finalReport ? "Compte rendu généré" : "En entretien");
  };

  const handleCvUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setCvFileName(file.name);
    setUploadingCv(true);
    setStatus("Extraction automatique du CV...");

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch("/api/extract-cv", {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error || "Impossible d'extraire le CV.");
      }
      setCvText(data?.text || "");
      setStatus("CV importé et extrait automatiquement ✅");
    } catch (error) {
      setStatus(`Erreur extraction CV: ${error instanceof Error ? error.message : "inconnue"}`);
    } finally {
      setUploadingCv(false);
      event.target.value = "";
    }
  };

  const speak = (text: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "fr-FR";
    utter.rate = 1;
    utter.onstart = () => {
      speakingRef.current = true;
      if (recognitionRef.current && listening) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
    };
    utter.onend = () => {
      speakingRef.current = false;
      if (recognitionRef.current && listening) {
        try {
          recognitionRef.current.start();
        } catch {}
      }
    };
    window.speechSynthesis.speak(utter);
  };

  const startInterview = async () => {
    const initMsg: Msg = {
      role: "user",
      text: "Bonjour, je suis prêt pour commencer l'entretien.",
    };
    const initialHistory = [initMsg];
    setMessages(initialHistory);
    setStatus("Démarrage...");
    setSecondsLeft(durationMinutes * 60);
    await sendToGemini(false, initialHistory);
    if (!textMode) {
      startListening();
    }
  };

  const stopInterview = async () => {
    setListening(false);
    setStatus("Entretien stoppé");
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
    }
  };

  const startListening = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = "fr-FR";
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = async (event: any) => {
      const last = event.results[event.results.length - 1];
      if (!last?.isFinal) return;
      const text = String(last[0]?.transcript || "").trim();
      if (!text) return;
      setMessages((prev) => {
        const next = [...prev, { role: "user" as const, text }];
        sendToGemini(false, next);
        return next;
      });
    };
    rec.onend = () => {
      if (listening && !speakingRef.current) {
        try {
          rec.start();
        } catch {}
      }
    };
    recognitionRef.current = rec;
    setListening(true);
    try {
      rec.start();
      setStatus("En entretien");
    } catch {}
  };

  // Camera toggle
  const toggleCamera = useCallback(async () => {
    if (cameraActive) {
      // Stop camera
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
      setCameraActive(false);
    } else {
      // Start camera
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraActive(true);
      } catch {
        setStatus("Impossible d'accéder à la caméra");
      }
    }
  }, [cameraActive]);

  // Clean up camera on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  // Text mode toggle
  const toggleTextMode = () => {
    setTextMode((prev) => {
      const next = !prev;
      if (next) {
        // Switching to text mode: stop voice recognition
        if (recognitionRef.current) {
          try {
            recognitionRef.current.stop();
          } catch {}
        }
        setListening(false);
      }
      return next;
    });
  };

  // Send typed text
  const sendTextMessage = () => {
    const text = textInput.trim();
    if (!text) return;
    setTextInput("");
    setMessages((prev) => {
      const next = [...prev, { role: "user" as const, text }];
      sendToGemini(false, next);
      return next;
    });
  };

  // Auto-scroll chat
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (secondsLeft === null) return;
    if (secondsLeft <= 0) {
      setSecondsLeft(null);
      setListening(false);
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
      sendToGemini(true);
      return;
    }
    const id = setTimeout(() => setSecondsLeft((s) => (s ?? 0) - 1), 1000);
    return () => clearTimeout(id);
  }, [secondsLeft]);

  const mmss = useMemo(() => {
    if (secondsLeft === null) return "--:--";
    const m = Math.floor(secondsLeft / 60)
      .toString()
      .padStart(2, "0");
    const s = (secondsLeft % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }, [secondsLeft]);

  return (
    <div style={{ background: "#00040f", minHeight: "100vh" }}>
      {/* ── Navbar ── */}
      <div className="container">
        <nav className="navbar">
          <div className="navbar-brand">
            🎙️ <span className="text-gradient">InterviewSim</span>
          </div>
          <ul className="navbar-links">
            <li><a href="#config">Configuration</a></li>
            <li><a href="#interview">Entretien</a></li>
          </ul>
        </nav>
      </div>

      {/* ── Hero ── */}
      <div className="container">
        <section className="hero">
          <h1>
            Simulez vos <span className="text-gradient">Entretiens</span> d&apos;Embauche
          </h1>
          <p>
            Entraînez-vous avec un recruteur IA. Importez votre CV, configurez le poste
            et lancez un entretien réaliste — par la voix ou par écrit.
          </p>
        </section>
      </div>

      {/* ── Features ── */}
      <div className="container">
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", justifyContent: "center", marginBottom: 40 }}>
          <div className="feature-card" style={{ flex: "1 1 200px", maxWidth: 320 }}>
            <div className="feature-icon">🎤</div>
            <div>
              <h3>Entretien Vocal</h3>
              <p>Répondez naturellement par la voix grâce à la reconnaissance vocale.</p>
            </div>
          </div>
          <div className="feature-card" style={{ flex: "1 1 200px", maxWidth: 320 }}>
            <div className="feature-icon">✍️</div>
            <div>
              <h3>Réponse Écrite</h3>
              <p>Préférez taper vos réponses ? Activez le mode texte en un clic.</p>
            </div>
          </div>
          <div className="feature-card" style={{ flex: "1 1 200px", maxWidth: 320 }}>
            <div className="feature-icon">📹</div>
            <div>
              <h3>Caméra</h3>
              <p>Activez votre webcam pour vous entraîner dans des conditions réelles.</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Configuration ── */}
      <div className="container" id="config">
        <div className="card">
          <h2>⚙️ Configuration de l&apos;entretien</h2>
          <div className="grid two">
            <div>
              <label>Type de candidature</label>
              <select
                value={applicationType}
                onChange={(e) => setApplicationType(e.target.value)}
              >
                <option>Emploi</option>
                <option>Stage</option>
                <option>Alternance</option>
                <option>Freelance</option>
                <option>Autre</option>
              </select>
            </div>
            <div>
              <label>Durée (minutes)</label>
              <input
                type="number"
                min={5}
                max={90}
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(Number(e.target.value || 20))}
              />
            </div>
            <div>
              <label>Intitulé du poste</label>
              <input
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="Data Analyst Marketing"
              />
            </div>
            <div>
              <label>Description du poste (optionnel)</label>
              <textarea
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
              />
            </div>
            <div style={{ gridColumn: "1/-1" }}>
              <label>Importer le CV (PDF, DOCX, TXT)</label>
              <input type="file" accept=".pdf,.doc,.docx,.txt" onChange={handleCvUpload} />
              <p className="meta" style={{ marginTop: 6 }}>
                {uploadingCv
                  ? "Extraction en cours..."
                  : cvFileName
                    ? `Fichier importé : ${cvFileName}`
                    : "Aucun fichier importé"}
              </p>
            </div>
            <div style={{ gridColumn: "1/-1" }}>
              <label>CV extrait automatiquement (modifiable)</label>
              <textarea
                value={cvText}
                onChange={(e) => setCvText(e.target.value)}
                placeholder="Le texte du CV s'affichera ici après import..."
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Interview Controls ── */}
      <div className="container" id="interview">
        <div className="card">
          <div className="status-bar">
            <div className="meta" style={{ fontSize: 14 }}>
              Statut: <strong style={{ color: "#fff" }}>{status}</strong> &nbsp;|&nbsp; ⏱ {mmss}
            </div>
            <div className="row">
              <button className="primary" onClick={startInterview}>
                ▶ Démarrer
              </button>
              <button
                className="secondary"
                onClick={startListening}
                disabled={!speechSupported || textMode}
              >
                🎤 Activer micro
              </button>
              <button
                className={`text-mode-btn${textMode ? " active" : ""}`}
                onClick={toggleTextMode}
              >
                ✍️ {textMode ? "Mode texte actif" : "Mode texte"}
              </button>
              <button
                className={`camera-btn${cameraActive ? " active" : ""}`}
                onClick={toggleCamera}
              >
                📹 {cameraActive ? "Couper caméra" : "Activer caméra"}
              </button>
              <button className="danger" onClick={stopInterview}>
                ⏹ Stop
              </button>
            </div>
          </div>
          {!speechSupported && !textMode && (
            <p className="meta" style={{ marginTop: 10 }}>
              ⚠️ Reconnaissance vocale non supportée sur ce navigateur (préférez Chrome).
              Utilisez le mode texte pour répondre.
            </p>
          )}
        </div>

        {/* ── Camera Preview ── */}
        {cameraActive && (
          <div className="camera-container">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="camera-preview"
            />
          </div>
        )}

        {/* ── Text Input ── */}
        {textMode && (
          <div className="card">
            <label>Tapez votre réponse :</label>
            <div className="text-input-area">
              <textarea
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Saisissez votre réponse ici..."
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendTextMessage();
                  }
                }}
              />
              <button className="primary" onClick={sendTextMessage} disabled={!textInput.trim()}>
                Envoyer
              </button>
            </div>
          </div>
        )}

        {/* ── Chat Log ── */}
        <div className="card log">
          {messages.length === 0
            ? "L'entretien apparaîtra ici..."
            : messages.map((m, i) => (
                <div key={i} className={m.role === "assistant" ? "msg-assistant" : "msg-user"}>
                  <div className="msg-role">
                    {m.role === "assistant" ? "🤖 Recruteur" : "👤 Vous"}
                  </div>
                  {m.text}
                </div>
              ))}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="container">
        <footer className="footer">
          <p>Interview Voice Simulator — Entraînez-vous. Progressez. Réussissez.</p>
        </footer>
      </div>
    </div>
  );
}
