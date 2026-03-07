import { NextRequest, NextResponse } from "next/server";

const MODEL = process.env.GEMINI_MODEL || "models/gemini-2.5-flash";

export async function POST(req: NextRequest) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "GEMINI_API_KEY manquante" }, { status: 500 });
  }

  const { cvText, jobTitle, jobDescription } = await req.json();

  if (!cvText || !jobTitle) {
    return NextResponse.json(
      { error: "CV et intitulé du poste requis pour calculer le score ATS." },
      { status: 400 }
    );
  }

  const prompt = [
    "Tu es un système ATS (Applicant Tracking System) expert en recrutement.",
    "Analyse le CV ci-dessous par rapport au poste indiqué et donne un score de compatibilité sur 100.",
    "",
    `Poste ciblé: ${jobTitle}`,
    jobDescription ? `Description du poste:\n${jobDescription}` : "",
    "",
    `CV du candidat:\n${cvText}`,
    "",
    "Réponds UNIQUEMENT au format JSON suivant, sans commentaire ni balise markdown:",
    '{"score": <nombre entre 0 et 100>, "details": "<résumé en 1-2 phrases des points forts et lacunes>"}',
  ]
    .filter(Boolean)
    .join("\n");

  try {
    const resp = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/${MODEL}:generateContent?key=${apiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.2 },
        }),
      }
    );

    if (!resp.ok) {
      const err = await resp.text();
      return NextResponse.json({ error: err }, { status: 500 });
    }

    const data = await resp.json();
    const raw =
      data?.candidates?.[0]?.content?.parts
        ?.map((p: { text?: string }) => p.text || "")
        .join("\n")
        .trim() || "";

    // Try to parse JSON from the response
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      const score = Math.max(0, Math.min(100, Math.round(Number(parsed.score) || 0)));
      return NextResponse.json({ score, details: parsed.details || "" });
    }

    return NextResponse.json({ error: "Impossible de parser le score ATS." }, { status: 500 });
  } catch (error) {
    return NextResponse.json(
      { error: `Erreur calcul ATS: ${error instanceof Error ? error.message : "inconnue"}` },
      { status: 500 }
    );
  }
}
