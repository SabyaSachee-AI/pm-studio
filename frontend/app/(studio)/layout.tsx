"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { CommandPalette } from "@/components/layout/CommandPalette";
import { Header } from "@/components/layout/header";
import { Sidebar } from "@/components/layout/sidebar";
import { api, type UserResponse } from "@/lib/api";

export default function StudioLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    api
      .me()
      .then((currentUser) => {
        setUser(currentUser);
      })
      .catch(() => {
        api.clearTokens();
        router.replace("/login");
      });
  }, [router]);

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-white" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-gray-950 text-white">
      <CommandPalette />
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Header user={user} />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
