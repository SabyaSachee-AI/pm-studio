import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "PM Studio",
  description: "The Ultimate Web App Ecosystem",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <head>
        {/* Tabler icon webfont — powers all `ti ti-*` icons across the app */}
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3/dist/tabler-icons.min.css"
        />
      </head>
      <body className="min-h-full flex flex-col bg-gray-950 font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
