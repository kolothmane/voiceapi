"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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

  const recognitionRef = useRef<any>(null);
  const speakingRef = useRef(false);

  const speechSupported = typeof window !== "undefined" && (!!window.SpeechRecognition || !!window.webkitSpeechRecognition);

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

  const speak = (text: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "fr-FR";
    utter.rate = 1;
    utter.onstart = () => {
      speakingRef.current = true;
      if (recognitionRef.current && listening) {
        try { recognitionRef.current.stop(); } catch {}
      }
    };
    utter.onend = () => {
      speakingRef.current = false;
      if (recognitionRef.current && listening) {
        try { recognitionRef.current.start(); } catch {}
      }
    };
    window.speechSynthesis.speak(utter);
  };

  const startInterview = async () => {
    const initMsg: Msg = { role: "user", text: "Bonjour, je suis prêt pour commencer l'entretien." };
    const initialHistory = [initMsg];
    setMessages(initialHistory);
    setStatus("Démarrage...");
    setSecondsLeft(durationMinutes * 60);
    await sendToGemini(false, initialHistory);
    startListening();
  };

  const stopInterview = async () => {
    setListening(false);
    setStatus("Entretien stoppé");
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
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
        try { rec.start(); } catch {}
      }
    };
    recognitionRef.current = rec;
    setListening(true);
    try { rec.start(); setStatus("En entretien"); } catch {}
  };

  useEffect(() => {
    if (secondsLeft === null) return;
    if (secondsLeft <= 0) {
      setSecondsLeft(null);
      setListening(false);
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch {}
      }
      sendToGemini(true);
      return;
    }
    const id = setTimeout(() => setSecondsLeft((s) => (s ?? 0) - 1), 1000);
    return () => clearTimeout(id);
  }, [secondsLeft]);

  const mmss = useMemo(() => {
    if (secondsLeft === null) return "--:--";
    const m = Math.floor(secondsLeft / 60).toString().padStart(2, "0");
    const s = (secondsLeft % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }, [secondsLeft]);

  return (
    <main className="container">
      <div className="card">
        <h1>🎙️ Interview Voice Simulator</h1>
        <p className="meta">Déployable sur Vercel — clé serveur via variable d&apos;environnement <code>GEMINI_API_KEY</code>.</p>
      </div>

      <div className="card grid two">
        <div>
          <label>Type de candidature</label>
          <select value={applicationType} onChange={(e) => setApplicationType(e.target.value)}>
            <option>Emploi</option><option>Stage</option><option>Alternance</option><option>Freelance</option><option>Autre</option>
          </select>
        </div>
        <div>
          <label>Durée (minutes)</label>
          <input type="number" min={5} max={90} value={durationMinutes} onChange={(e) => setDurationMinutes(Number(e.target.value || 20))} />
        </div>
        <div>
          <label>Intitulé du poste</label>
          <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Data Analyst Marketing" />
        </div>
        <div>
          <label>Description du poste (optionnel)</label>
          <textarea value={jobDescription} onChange={(e) => setJobDescription(e.target.value)} />
        </div>
        <div style={{ gridColumn: "1/-1" }}>
          <label>CV (texte)</label>
          <textarea value={cvText} onChange={(e) => setCvText(e.target.value)} placeholder="Collez ici votre CV..." />
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div className="meta">Statut: {status} | Timer: {mmss}</div>
          <div className="row">
            <button className="primary" onClick={startInterview}>Démarrer</button>
            <button className="secondary" onClick={startListening} disabled={!speechSupported}>Activer micro</button>
            <button className="danger" onClick={stopInterview}>Stop</button>
          </div>
        </div>
        {!speechSupported && <p className="meta">⚠️ Reconnaissance vocale non supportée sur ce navigateur (préférez Chrome).</p>}
      </div>

      <div className="card log">
        {messages.length === 0 ? "L'entretien apparaîtra ici..." : messages.map((m, i) => (
          <div key={i}><b>{m.role === "assistant" ? "Recruteur" : "Vous"}:</b> {m.text}</div>
        ))}
      </div>
    </main>
  );
}
