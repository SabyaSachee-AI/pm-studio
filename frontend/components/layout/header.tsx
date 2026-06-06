"use client";

import { Button } from "@/components/ui/button";
import { api, type UserResponse } from "@/lib/api";
import { useRouter } from "next/navigation";

interface HeaderProps {
  user: UserResponse;
}

export function Header({ user }: HeaderProps) {
  const router = useRouter();

  async function handleLogout() {
    await api.logout();
    router.replace("/login");
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-800 bg-gray-950 px-6">
      <p className="text-sm text-gray-400">Signed in as {user.full_name}</p>
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-gray-700 px-2 py-0.5 text-xs text-gray-300">
          {user.role.replace(/_/g, " ")}
        </span>
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </header>
  );
}
