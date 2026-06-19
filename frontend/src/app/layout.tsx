import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { PasswordGate } from "@/components/PasswordGate";

export const metadata = {
  title: "JobPilot",
  description: "Job application intelligence layer",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Newsreader:ital,wght@0,400;0,500;0,600;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        <style>{`
          html, body { margin:0; padding:0; height:100%; }
          .fade-in { animation: fadeIn .3s ease-out; }
          @keyframes fadeIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
          @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.4; } }
        `}</style>
      </head>
      <body className="jp-app">
        <PasswordGate>
          <div className="jp-shell">
            <Sidebar />
            <main className="jp-main">{children}</main>
          </div>
        </PasswordGate>
      </body>
    </html>
  );
}
