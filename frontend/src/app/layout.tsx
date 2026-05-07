import type { Metadata } from "next";
import Sidebar from "@/components/sidebar/Sidebar";
import { FirstRunWizard } from "@/components/wizard/FirstRunWizard";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepoLens",
  description: "Solo-maintainer cockpit for your OSS surface",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body>
        <FirstRunWizard>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 p-8 overflow-auto">{children}</main>
          </div>
        </FirstRunWizard>
      </body>
    </html>
  );
}
