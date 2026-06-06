"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, type PRD } from "@/lib/api";

export default function PrdPortalPage() {
  const { id } = useParams<{ id: string }>();
  const [prd, setPrd] = useState<PRD | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!api.getAccessToken()) {
      setError("Please log in as a client to review this PRD.");
      return;
    }
    api.getPrd(id).then(setPrd).catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 p-6 text-center text-gray-300">
        <div>
          <p>{error}</p>
          <a href="/login" className="mt-4 inline-block text-blue-400 underline">
            Go to login
          </a>
        </div>
      </div>
    );
  }

  if (!prd?.content_json) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 p-8 text-white">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-2xl font-semibold">PRD review portal</h1>
        <p className="text-sm text-gray-400">Status: {prd.status} · Version {prd.version}</p>
        <p className="text-sm text-gray-300">
          {String(prd.content_json.executive_summary)}
        </p>
        {prd.status === "submitted" && (
          <Button onClick={() => api.approvePrd(id).then(setPrd)}>
            Approve PRD
          </Button>
        )}
        {prd.status === "approved" && (
          <p className="text-green-400">This PRD has been approved.</p>
        )}
      </div>
    </div>
  );
}
