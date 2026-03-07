import { NextRequest, NextResponse } from "next/server";

const MODEL = process.env.GEMINI_MODEL || "models/gemini-2.5-flash";

function extractTextFromGeminiResponse(data: any): string {
  return (
    data?.candidates?.[0]?.content?.parts
      ?.map((p: { text?: string }) => p.text || "")
      .join("\n")
      .trim() || ""
  );
}

export async function POST(req: NextRequest) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "GEMINI_API_KEY manquante" }, { status: 500 });
  }

  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Fichier CV manquant." }, { status: 400 });
  }

  const fileName = (file.name || "cv").toLowerCase();
  const mimeType = file.type || "application/octet-stream";

  try {
    // TXT: extraction locale simple (plus rapide et moins coûteuse)
    if (mimeType.startsWith("text/") || fileName.endsWith(".txt")) {
      const text = await file.text();
      return NextResponse.json({ text: text.trim() });
    }

    // PDF/DOCX/etc: déléguer à Gemini avec inlineData
    const bytes = Buffer.from(await file.arrayBuffer());
    const base64 = bytes.toString("base64");

    const payload = {
      contents: [
        {
          role: "user",
          parts: [
            {
              text:
                "Extrais le texte du CV ci-joint. Réponds uniquement avec le texte brut du CV, sans commentaire ni balises.",
            },
            {
              inlineData: {
                mimeType,
                data: base64,
              },
            },
          ],
        },
      ],
      generationConfig: { temperature: 0.1 },
    };

    const resp = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/${MODEL}:generateContent?key=${apiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );

    if (!resp.ok) {
      const err = await resp.text();
      return NextResponse.json({ error: err }, { status: 500 });
    }

    const data = await resp.json();
    const text = extractTextFromGeminiResponse(data);

    if (!text) {
      return NextResponse.json({ error: "Extraction vide depuis le CV." }, { status: 500 });
    }

    return NextResponse.json({ text });
  } catch (error) {
    return NextResponse.json(
      { error: `Échec extraction CV: ${error instanceof Error ? error.message : "erreur inconnue"}` },
      { status: 500 }
    );
  }
}
