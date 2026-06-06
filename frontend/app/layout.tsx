import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "PM Studio",
  description: "AI-powered project management",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <body className="min-h-full flex flex-col bg-gray-950 font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
