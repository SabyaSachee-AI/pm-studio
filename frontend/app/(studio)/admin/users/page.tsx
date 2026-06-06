"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { RoleBadge } from "@/components/ui/role-badge";
import { api, type UserResponse } from "@/lib/api";
import { formatRoleLabel } from "@/lib/roles";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");

  useEffect(() => {
    api.listUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    await api.createUser({ email, full_name: fullName, password, role });
    setEmail("");
    setFullName("");
    setPassword("");
    setUsers(await api.listUsers());
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">User management</h1>
      <form onSubmit={handleCreate} className="grid max-w-lg gap-2">
        <input
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          placeholder="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />
        <input
          type="password"
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <select
          aria-label="Role"
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          {[
            "studio_owner",
            "studio_admin",
            "project_manager",
            "business_analyst",
            "architect",
            "code_creator",
            "qa_engineer",
            "client",
            "viewer",
          ].map((r) => (
            <option key={r} value={r}>
              {formatRoleLabel(r)}
            </option>
          ))}
        </select>
        <Button type="submit">Create user</Button>
      </form>
      <div className="rounded-xl border border-gray-800">
        {users.map((u) => (
          <div
            key={u.id}
            className="flex items-center justify-between border-b border-gray-800 px-4 py-3 last:border-0"
          >
            <div>
              <p className="font-medium">{u.full_name}</p>
              <p className="text-xs text-gray-500">{u.email}</p>
            </div>
            <div className="flex items-center gap-3">
              <RoleBadge role={u.role} />
              <span
                className={`text-xs ${u.is_active ? "text-green-400" : "text-red-400"}`}
              >
                {u.is_active ? "Active" : "Inactive"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
