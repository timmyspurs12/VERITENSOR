import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "VERITENSOR — The decentralized verification layer for machine intelligence",
  description:
    "Miners compete to produce reliable AI answers. Validators independently verify them. Performance determines reputation and emission.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg font-sans text-[15px] text-ink-1 antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
