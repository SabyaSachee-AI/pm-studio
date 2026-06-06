"use client";

import { useEffect, useState } from "react";
import { api, type UserResponse } from "@/lib/api";

export default function DashboardPage() {
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    api.me().then(setUser);
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-3">
        {[
          { title: "Requirements", desc: "Upload PDFs and run AI analysis" },
          { title: "PRDs", desc: "Generate and approve product requirements" },
          { title: "SRS", desc: "Generate IEEE 830 specifications" },
        ].map((card) => (
          <div
            key={card.title}
            className="rounded-xl border border-gray-800 bg-gray-900 p-5"
          >
            <h2 className="font-medium">{card.title}</h2>
            <p className="mt-2 text-sm text-gray-400">{card.desc}</p>
          </div>
        ))}
      </div>
      {user && (
        <p className="text-sm text-gray-500">
          Welcome back, {user.full_name}. Use the sidebar to manage your studio.
        </p>
      )}
    </div>
  );
}
