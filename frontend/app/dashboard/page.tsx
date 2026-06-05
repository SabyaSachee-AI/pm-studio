"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { api, type UserResponse } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
      return;
    }

    api
      .me()
      .then((currentUser) => {
        setUser(currentUser);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        router.replace("/login");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [router]);

  function handleLogout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.replace("/login");
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-white"
          role="status"
          aria-label="Loading"
        />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-950 px-6 py-10">
      <div className="mx-auto max-w-3xl">
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-white">
            PM Studio dashboard
          </h1>
          <Button variant="outline" onClick={handleLogout}>
            Log out
          </Button>
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
          <p className="text-lg text-white">Welcome, {user.full_name}</p>
          <span className="mt-3 inline-block rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-sm text-gray-300">
            {user.role.replace(/_/g, " ")}
          </span>
        </div>
      </div>
    </div>
  );
}
