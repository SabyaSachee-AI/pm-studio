"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [router]);

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
