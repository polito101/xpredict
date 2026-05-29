/**
 * Plan 08-03 — User detail client island (header + tabs + ban/unban dialogs).
 *
 * Owns the live `UserDetail` state so a ban / unban / recharge updates the
 * header (status, ban button variant), the Profile tab, and the Wallet balance
 * consistently from one source of truth. The server page passes the initial
 * fetch; mutations replace it with the `UserDetail` the backend returns, and the
 * recharge path re-fetches the user (via `fetchUserDetail`) to refresh balance.
 *
 * Header per UI-SPEC: email heading, display name, metadata row (joined / last
 * active), and a ban/unban button top-right — `destructive` "Ban User" when
 * active, `outline` "Unban User" when banned. Three tabs (Profile / Wallet /
 * Bets); tab switch is client-side only (no URL change), each tab owns its
 * pagination state.
 */
"use client";

import * as React from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ProfileTab } from "@/components/admin/profile-tab";
import { WalletTab } from "@/components/admin/wallet-tab";
import { BetsTab } from "@/components/admin/bets-tab";
import { BanConfirmDialog } from "@/components/admin/ban-confirm-dialog";
import { UnbanConfirmDialog } from "@/components/admin/unban-confirm-dialog";
import { fetchUserDetail } from "@/lib/admin-api";
import type { UserDetail } from "@/lib/admin-types";
import { formatDate, formatRelativeTime } from "@/lib/admin-format";

export function UserDetailTabs({ initialUser }: { initialUser: UserDetail }) {
  const [user, setUser] = React.useState<UserDetail>(initialUser);
  const [banOpen, setBanOpen] = React.useState(false);
  const [unbanOpen, setUnbanOpen] = React.useState(false);

  const banned = user.status === "banned";

  // Recharge mutates the balance server-side; re-pull the detail to reflect it.
  const refetchUser = React.useCallback(async () => {
    try {
      const fresh = await fetchUserDetail(user.id);
      setUser(fresh);
    } catch {
      // Non-fatal: the recharge succeeded; a stale balance corrects on reload.
    }
  }, [user.id]);

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold tracking-tight">{user.email}</h1>
          {user.display_name && (
            <p className="text-base text-zinc-600 dark:text-zinc-400">
              {user.display_name}
            </p>
          )}
          <p className="text-sm text-zinc-500">
            Joined: {formatDate(user.created_at)}
            {" | "}
            Last active: {formatRelativeTime(user.last_activity)}
          </p>
        </div>
        {banned ? (
          <Button variant="outline" onClick={() => setUnbanOpen(true)}>
            Unban User
          </Button>
        ) : (
          <Button variant="destructive" onClick={() => setBanOpen(true)}>
            Ban User
          </Button>
        )}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="wallet">Wallet</TabsTrigger>
          <TabsTrigger value="bets">Bets</TabsTrigger>
        </TabsList>
        <TabsContent value="profile" className="pt-6">
          <ProfileTab user={user} />
        </TabsContent>
        <TabsContent value="wallet" className="pt-6">
          <WalletTab user={user} onRecharged={refetchUser} />
        </TabsContent>
        <TabsContent value="bets" className="pt-6">
          <BetsTab userId={user.id} />
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <BanConfirmDialog
        open={banOpen}
        onOpenChange={setBanOpen}
        userId={user.id}
        onBanned={setUser}
      />
      <UnbanConfirmDialog
        open={unbanOpen}
        onOpenChange={setUnbanOpen}
        userId={user.id}
        onUnbanned={setUser}
      />
    </div>
  );
}
