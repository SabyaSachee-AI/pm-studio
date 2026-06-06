"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button, studioButtonSurfaceClassName } from "@/components/ui/button";
import { RoleBadge } from "@/components/ui/role-badge";
import { api, type Notification, type UserResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface HeaderProps {
  user: UserResponse;
}

export function Header({ user }: HeaderProps) {
  const router = useRouter();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.listNotifications(true).then(setNotifications).catch(() => setNotifications([]));
  }, []);

  async function handleLogout() {
    await api.logout();
    router.replace("/login");
  }

  async function handleRead(id: string, link: string | null) {
    await api.markNotificationRead(id);
    setNotifications((prev) => prev.filter((n) => n.id !== id));
    if (link) router.push(link);
    setOpen(false);
  }

  return (
    <header className="relative flex h-14 items-center justify-between border-b border-gray-800 bg-gray-950 px-6">
      <p className="text-sm text-gray-400">Signed in as {user.full_name}</p>
      <div className="flex items-center gap-3">
        <div className="relative">
          <Button size="sm" onClick={() => setOpen((v) => !v)}>
            Notifications
            {notifications.length > 0 && (
              <span className="ml-1.5 rounded-full bg-blue-600 px-1.5 text-[0.65rem] text-white">
                {notifications.length}
              </span>
            )}
          </Button>
          {open && (
            <div className="absolute right-0 top-10 z-50 w-72 rounded-md border border-white/20 bg-[#0a1628] p-2 shadow-lg">
              {notifications.length === 0 ? (
                <p className="px-2 py-3 text-xs text-gray-400">No unread notifications</p>
              ) : (
                notifications.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    className={cn(
                      "block w-full rounded-lg px-2 py-2 text-left text-sm text-white",
                      studioButtonSurfaceClassName,
                    )}
                    onClick={() => handleRead(n.id, n.link)}
                  >
                    <p className="font-medium">{n.title}</p>
                    <p className="text-xs text-gray-400">{n.message}</p>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
        <RoleBadge role={user.role} />
        <Button size="sm" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </header>
  );
}
