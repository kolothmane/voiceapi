import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Interview Voice Simulator",
  description: "Simulation d'entretien vocal avec Gemini",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
