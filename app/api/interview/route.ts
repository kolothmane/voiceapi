import { NextRequest, NextResponse } from "next/server";

const MODEL = process.env.GEMINI_MODEL || "models/gemini-2.5-flash";

function buildPrompt(payload: {
  cvText: string;
  jobTitle: string;
  jobDescription: string;
  applicationType: string;
  durationMinutes: number;
  history: Array<{ role: "user" | "assistant"; text: string }>;
  finalReport: boolean;
}) {
  const base = [
    "Tu es un recruteur expérimenté. Tu mènes une simulation d'entretien d'embauche en français.",
    "Pose une question à la fois, concise, puis attends la réponse.",
    `Type de candidature: ${payload.applicationType || "Non précisé"}`,
    `Poste ciblé: ${payload.jobTitle || "Non précisé"}`,
    `Durée cible: ${payload.durationMinutes} minutes`,
    payload.jobDescription ? `Description du poste:\n${payload.jobDescription}` : "",
    payload.cvText ? `CV du candidat:\n${payload.cvText}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");

  const history = payload.history
    .map((m) => `${m.role === "user" ? "Candidat" : "Recruteur"}: ${m.text}`)
    .join("\n");

  const objective = payload.finalReport
    ? "Le temps est écoulé. Termine l'entretien et donne uniquement un compte rendu structuré: résumé, points forts, axes d'amélioration, conseils."
    : "Continue l'entretien normalement avec la prochaine question la plus pertinente.";

  return `${base}\n\nHistorique:\n${history || "(début)"}\n\n${objective}`;
}

export async function POST(req: NextRequest) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "GEMINI_API_KEY manquante" }, { status: 500 });
  }

  const body = await req.json();
  const prompt = buildPrompt(body);

  const resp = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/${MODEL}:generateContent?key=${apiKey}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.7 },
      }),
    }
  );

  if (!resp.ok) {
    const err = await resp.text();
    return NextResponse.json({ error: err }, { status: 500 });
  }

  const data = await resp.json();
  const text =
    data?.candidates?.[0]?.content?.parts
      ?.map((p: { text?: string }) => p.text || "")
      .join("\n")
      .trim() || "";

  return NextResponse.json({ text });
}
