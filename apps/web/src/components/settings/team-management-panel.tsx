"use client";

import {
  ChevronDown,
  MailPlus,
  RefreshCw,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ContentCard } from "@/components/dashboard/content-card";
import { Button } from "@/components/ui/button";
import type {
  ApiErrorPayload,
  Invitation,
  OrganizationMember,
  OrganizationRole,
} from "@/lib/types";
import { apiErrorMessage, cn, formatDate } from "@/lib/utils";

const inviteRoles: { label: string; value: OrganizationRole }[] = [
  { label: "Accountant", value: "accountant" },
  { label: "Approver", value: "approver" },
  { label: "Viewer", value: "viewer" },
  { label: "Admin", value: "admin" },
  { label: "Owner", value: "owner" },
];

const roleTone: Record<OrganizationRole, string> = {
  owner: "border-accent/30 bg-accent-soft text-accent-ink",
  admin: "border-cyan/30 bg-cyan/10 text-cyan-ink",
  accountant: "border-success/30 bg-success/10 text-success",
  approver: "border-gold/30 bg-gold/10 text-gold",
  viewer: "border-line bg-surface-subtle text-ink-secondary",
};

export function TeamManagementPanel() {
  const { activeOrganizationId, user } = useAuth();
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrganizationRole>("accountant");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [lastInviteToken, setLastInviteToken] = useState("");
  const [lastInviteUrl, setLastInviteUrl] = useState("");
  const [changingRoleFor, setChangingRoleFor] = useState<string>("");

  async function changeMemberRole(
    member: OrganizationMember,
    nextRole: OrganizationRole,
  ) {
    if (!activeOrganizationId || nextRole === member.role) return;
    setChangingRoleFor(member.user_id);
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        `/api/organizations/${activeOrganizationId}/members/${member.user_id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role: nextRole }),
        },
      );
      const payload = (await response.json().catch(() => ({}))) as
        | OrganizationMember
        | ApiErrorPayload;
      if (!response.ok) {
        throw new Error(apiErrorMessage(payload, "Role could not be changed."));
      }
      setMembers((current) =>
        current.map((entry) =>
          entry.user_id === member.user_id
            ? { ...entry, role: nextRole }
            : entry,
        ),
      );
      setMessage(`${member.full_name || member.email} is now ${nextRole}.`);
    } catch (changeError) {
      setError((changeError as Error).message);
    } finally {
      setChangingRoleFor("");
    }
  }

  const currentRole = useMemo(
    () =>
      user?.memberships.find(
        (membership) => membership.organization_id === activeOrganizationId,
      )?.role,
    [activeOrganizationId, user?.memberships],
  );
  const canManageTeam = currentRole === "owner" || currentRole === "admin";

  const refreshTeam = useCallback(async () => {
    if (!activeOrganizationId || !canManageTeam) return;
    setLoading(true);
    setError("");
    try {
      const [membersResponse, invitationsResponse] = await Promise.all([
        fetch(`/api/organizations/${activeOrganizationId}/members`),
        fetch(`/api/organizations/${activeOrganizationId}/invitations`),
      ]);
      if (!membersResponse.ok || !invitationsResponse.ok) {
        throw new Error("Team details could not be loaded.");
      }
      setMembers((await membersResponse.json()) as OrganizationMember[]);
      setInvitations((await invitationsResponse.json()) as Invitation[]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Team details could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }, [activeOrganizationId, canManageTeam]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void refreshTeam();
    }, 0);
    return () => window.clearTimeout(handle);
  }, [refreshTeam]);

  async function sendInvite() {
    if (!activeOrganizationId || !email.trim()) return;
    setSending(true);
    setError("");
    setMessage("");
    setLastInviteToken("");
    setLastInviteUrl("");
    try {
      const response = await fetch(
        `/api/organizations/${activeOrganizationId}/invitations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, role }),
        },
      );
      const payload = (await response.json().catch(() => ({}))) as
        | Invitation
        | ApiErrorPayload;
      if (!response.ok) {
        throw new Error(apiErrorMessage(payload, "Invite could not be sent."));
      }
      const token =
        "invitation_token" in payload ? (payload.invitation_token ?? "") : "";
      setMessage(
        token
          ? `Invitation prepared for ${email.trim()}.`
          : `Invitation email sent to ${email.trim()}.`,
      );
      setLastInviteToken(token);
      setLastInviteUrl(
        token
          ? `${window.location.origin}/invite?token=${encodeURIComponent(token)}`
          : "",
      );
      setEmail("");
      setRole("accountant");
      await refreshTeam();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Invite could not be sent.",
      );
    } finally {
      setSending(false);
    }
  }

  if (!canManageTeam) {
    return (
      <ContentCard
        title="Team access"
        subtitle="Only owners and admins can invite users or view workspace access."
      >
        <div className="rounded-2xl border border-line bg-surface-subtle p-5 text-sm font-semibold text-ink-secondary">
          Your current role is {currentRole ?? "viewer"}. Ask an owner or admin
          to manage team access for this workspace.
        </div>
      </ContentCard>
    );
  }

  return (
    <ContentCard
      title="Team access"
      subtitle="Invite accountants, approvers, viewers, and admins into this client workspace."
      action={
        <Button size="sm" onClick={refreshTeam} disabled={loading}>
          <RefreshCw size={14} className={cn(loading && "animate-spin")} />
          Refresh
        </Button>
      }
    >
      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)] 2xl:grid-cols-[minmax(300px,400px)_minmax(0,1fr)]">
        <div className="min-w-0 rounded-2xl border border-line bg-canvas p-4">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-soft text-accent-ink">
              <MailPlus size={18} />
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">Invite teammate</p>
              <p className="text-xs font-semibold text-ink-secondary">
                Role controls what they can view, approve, and post.
              </p>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            <label className="block">
              <span className="text-xs font-semibold uppercase text-ink-muted">
                Work email
              </span>
              <input
                className="mt-2 h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm font-semibold text-ink outline-none transition focus:border-accent"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                type="email"
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold uppercase text-ink-muted">
                Role
              </span>
              <select
                className="mt-2 h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm font-semibold text-ink outline-none transition focus:border-accent"
                value={role}
                onChange={(event) =>
                  setRole(event.target.value as OrganizationRole)
                }
              >
                {inviteRoles.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <Button
              className="w-full"
              variant="primary"
              onClick={sendInvite}
              disabled={sending || !email.trim()}
            >
              {sending ? "Preparing invite..." : "Create invite"}
            </Button>
            {message && (
              <div className="rounded-xl border border-success/25 bg-success/10 px-3 py-2 text-sm font-semibold text-success">
                {message}
              </div>
            )}
            {lastInviteToken && (
              <div className="rounded-xl border border-line bg-surface-subtle p-3">
                <p className="text-xs font-semibold uppercase text-ink-muted">
                  Invite link
                </p>
                <p className="mt-2 break-all font-mono text-xs text-ink">
                  {lastInviteUrl}
                </p>
                <p className="mt-3 text-xs font-semibold uppercase text-ink-muted">
                  Dev token
                </p>
                <p className="mt-2 break-all font-mono text-xs text-ink">
                  {lastInviteToken}
                </p>
              </div>
            )}
            {error && (
              <div className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm font-semibold text-danger">
                {error}
              </div>
            )}
          </div>
        </div>

        <div className="min-w-0 space-y-4">
          <div className="w-full max-w-full overflow-x-auto rounded-2xl border border-line">
            <div className="sm:min-w-[540px]">
              <div className="hidden grid-cols-[minmax(0,1fr)_120px_128px] gap-3 border-b border-line bg-surface-subtle px-4 py-3 text-xs font-semibold uppercase text-ink-muted sm:grid">
                <span>Member</span>
                <span>Role</span>
                <span>Last login</span>
              </div>
              {members.length ? (
                members.map((member) => (
                  <div
                    key={member.user_id}
                    className="grid grid-cols-1 gap-2 border-b border-line px-4 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_120px_128px] sm:items-center sm:gap-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-ink">
                        {member.full_name || member.email}
                      </p>
                      <p className="truncate text-xs font-semibold text-ink-secondary">
                        {member.email}
                      </p>
                    </div>
                    <div className="flex items-center justify-between gap-3 sm:contents">
                      {member.user_id === user?.id ? (
                        <RolePill role={member.role} />
                      ) : (
                        <label className="relative block">
                          <span className="sr-only">
                            Role for {member.email}
                          </span>
                          <select
                            value={member.role}
                            disabled={changingRoleFor === member.user_id}
                            onChange={(event) =>
                              void changeMemberRole(
                                member,
                                event.target.value as OrganizationRole,
                              )
                            }
                            title="Change role"
                            className={cn(
                              "h-9 w-full cursor-pointer appearance-none rounded-full border px-3 pr-8 text-xs font-semibold outline-none transition-colors focus:border-accent disabled:cursor-wait disabled:opacity-60",
                              roleTone[member.role],
                            )}
                          >
                            {inviteRoles.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <ChevronDown
                            size={14}
                            className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-current"
                          />
                        </label>
                      )}
                      <p className="text-xs font-semibold text-ink-secondary">
                        <span className="sm:hidden">Last login: </span>
                        {member.last_login_at
                          ? formatDate(member.last_login_at)
                          : "Not yet"}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="px-4 py-8 text-sm font-semibold text-ink-secondary">
                  {loading ? "Loading team..." : "No team members found."}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-canvas p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <ShieldCheck size={16} className="text-accent-ink" />
              Pending invitations
            </div>
            {invitations.length ? (
              <div className="space-y-2">
                {invitations.map((invitation) => (
                  <div
                    key={invitation.id}
                    className="flex flex-col gap-2 rounded-xl border border-line bg-surface px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <p className="text-sm font-semibold text-ink">
                        {invitation.email}
                      </p>
                      <p className="text-xs font-semibold text-ink-secondary">
                        Expires {formatDate(invitation.expires_at)}
                      </p>
                    </div>
                    <RolePill role={invitation.role} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-line bg-surface px-3 py-4 text-sm font-semibold text-ink-secondary">
                No pending invites.
              </div>
            )}
          </div>
        </div>
      </div>
    </ContentCard>
  );
}

function RolePill({ role }: { role: OrganizationRole }) {
  return (
    <span
      className={cn(
        "inline-flex h-8 w-fit items-center gap-2 rounded-full border px-3 text-xs font-semibold capitalize",
        roleTone[role],
      )}
    >
      <UserRoundCheck size={13} />
      {role}
    </span>
  );
}
