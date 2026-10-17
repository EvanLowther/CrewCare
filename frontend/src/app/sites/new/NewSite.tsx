"use client";

import { Lock } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMe } from "@/components/MeProvider";
import { SiteForm } from "@/components/SiteForm";
import { Card, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";

export function NewSite() {
  const { me, role, refresh } = useMe();
  const router = useRouter();

  if (!me) return <p className="text-sm text-muted">Loading…</p>;
  if (role !== "manager" && role !== "admin") {
    return (
      <Card>
        <EmptyState icon={Lock} title="Managers create sites" detail="Ask an admin to make you a manager." />
      </Card>
    );
  }
  return (
    <SiteForm
      submitLabel="Create site"
      onSubmit={async (v) => {
        const created = await api.createSite({ name: v.name, description: v.description || null, latitude: v.latitude, longitude: v.longitude });
        await refresh();
        router.push(`/sites/${created.site.id}/manage?new=1`);
      }}
    />
  );
}
