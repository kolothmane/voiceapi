import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Interview Voice Simulator",
  description: "Simulation d'entretien vocal avec Gemini",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800;900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
