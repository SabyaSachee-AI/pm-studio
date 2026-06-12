"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, type SRS } from "@/lib/api";

export default function SrsPortalPage() {
  const { id } = useParams<{ id: string }>();
  const [srs, setSrs] = useState<SRS | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getSrs(id)
      .then(setSrs)
      .catch((e: Error) =>
        setError(e.message || "Please log in as a client to review this SRS."),
      );
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

  if (!srs?.content_json) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 text-gray-400">
        Loading...
      </div>
    );
  }

  const content = srs.content_json;
  const summary =
    String(content.purpose ?? "") ||
    String(content.scope ?? "") ||
    String(content.introduction ?? "");

  return (
    <div className="min-h-screen bg-gray-950 p-8 text-white">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-2xl font-semibold">SRS review portal</h1>
        <p className="text-sm text-gray-400">
          Status: {srs.status} · Version {srs.version} · IEEE 830
        </p>
        {summary ? (
          <p className="whitespace-pre-wrap text-sm text-gray-300">{summary}</p>
        ) : null}
        {srs.status === "submitted" && (
          <Button onClick={() => api.approveSrs(id).then(setSrs)}>
            Approve SRS
          </Button>
        )}
        {srs.status === "approved" && (
          <p className="text-green-400">This SRS has been approved.</p>
        )}
      </div>
    </div>
  );
}
