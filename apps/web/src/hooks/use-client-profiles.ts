"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import type {
  AccountingSystem,
  ApiErrorPayload,
  ClientProfile,
  ClientProfilePayload,
} from "@/lib/types";
import { apiErrorMessage } from "@/lib/utils";

interface UseClientProfilesOptions {
  accountingSystem?: AccountingSystem;
}

function profileUrl(organizationId: string, profileId?: string) {
  const base = `/api/organizations/${organizationId}/client-profiles`;
  return profileId ? `${base}/${profileId}` : base;
}

async function readError(response: Response, fallback: string) {
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    return apiErrorMessage(payload, fallback);
  } catch {
    return fallback;
  }
}

export function useClientProfiles({
  accountingSystem,
}: UseClientProfilesOptions = {}) {
  const { activeOrganizationId: organizationId } = useAuth();
  const [profiles, setProfiles] = useState<ClientProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const loadProfiles = useCallback(
    async (signal?: AbortSignal) => {
      if (!organizationId) {
        setProfiles([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const query = new URLSearchParams();
        if (accountingSystem) query.set("accounting_system", accountingSystem);
        const suffix = query.toString() ? `?${query}` : "";
        const response = await fetch(`${profileUrl(organizationId)}${suffix}`, {
          cache: "no-store",
          signal,
        });
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to load client profiles."),
          );
        }
        setProfiles((await response.json()) as ClientProfile[]);
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setError((loadError as Error).message);
        }
      } finally {
        setLoading(false);
      }
    },
    [accountingSystem, organizationId],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void loadProfiles(controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadProfiles]);

  const createProfile = useCallback(
    async (payload: ClientProfilePayload) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(profileUrl(organizationId), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to create client profile."),
          );
        }
        const created = (await response.json()) as ClientProfile;
        setProfiles((current) => [created, ...current]);
        return created;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const updateProfile = useCallback(
    async (profileId: string, payload: Partial<ClientProfilePayload>) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(profileUrl(organizationId, profileId), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to update client profile."),
          );
        }
        const updated = (await response.json()) as ClientProfile;
        setProfiles((current) =>
          current.map((profile) => (profile.id === updated.id ? updated : profile)),
        );
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const setDefaultProfile = useCallback(
    async (profileId: string) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(
          `${profileUrl(organizationId, profileId)}/set-default`,
          { method: "POST" },
        );
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to set default client profile."),
          );
        }
        const updated = (await response.json()) as ClientProfile;
        setProfiles((current) =>
          current.map((profile) =>
            profile.accounting_system === updated.accounting_system
              ? { ...profile, is_default: profile.id === updated.id }
              : profile,
          ),
        );
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const submitProfileForReview = useCallback(
    async (profileId: string) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(
          `${profileUrl(organizationId, profileId)}/submit-review`,
          { method: "POST" },
        );
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to submit profile for review."),
          );
        }
        const updated = (await response.json()) as ClientProfile;
        setProfiles((current) =>
          current.map((profile) => (profile.id === updated.id ? updated : profile)),
        );
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const recommendProfileSettings = useCallback(
    async (profileId: string) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(
          `${profileUrl(organizationId, profileId)}/recommend-settings`,
          { method: "POST" },
        );
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to generate profile recommendations."),
          );
        }
        const updated = (await response.json()) as ClientProfile;
        setProfiles((current) =>
          current.map((profile) => (profile.id === updated.id ? updated : profile)),
        );
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const activateProfile = useCallback(
    async (profileId: string) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(
          `${profileUrl(organizationId, profileId)}/activate`,
          { method: "POST" },
        );
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to activate client profile."),
          );
        }
        const updated = (await response.json()) as ClientProfile;
        setProfiles((current) =>
          current.map((profile) => (profile.id === updated.id ? updated : profile)),
        );
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const deleteProfile = useCallback(
    async (profileId: string) => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const response = await fetch(profileUrl(organizationId, profileId), {
          method: "DELETE",
        });
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to delete client profile."),
          );
        }
        setProfiles((current) =>
          current.filter((profile) => profile.id !== profileId),
        );
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  const uploadTrainingSample = useCallback(
    async (profileId: string, file: File, notes = "") => {
      if (!organizationId) throw new Error("No active organization selected.");
      setSaving(true);
      setError("");
      try {
        const form = new FormData();
        form.set("file", file);
        form.set("sample_type", "invoice");
        form.set("notes", notes);
        const response = await fetch(
          `${profileUrl(organizationId, profileId)}/training-samples`,
          {
            method: "POST",
            body: form,
          },
        );
        if (!response.ok) {
          throw new Error(
            await readError(response, "Unable to upload training sample."),
          );
        }
        const updated = (await response.json()) as ClientProfile;
        setProfiles((current) =>
          current.map((profile) => (profile.id === updated.id ? updated : profile)),
        );
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [organizationId],
  );

  return {
    profiles,
    loading,
    saving,
    error,
    reload: () => loadProfiles(),
    createProfile,
    updateProfile,
    setDefaultProfile,
    submitProfileForReview,
    recommendProfileSettings,
    activateProfile,
    deleteProfile,
    uploadTrainingSample,
  };
}
