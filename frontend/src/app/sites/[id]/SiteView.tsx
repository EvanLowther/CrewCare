"use client";

import { use } from "react";

// Hours 8-12: conditions, active alerts (lightning countdown), score + factors, 48 h forecast,
// crew reports nearby. Data: api.site(Number(id)) -> SiteDetail.
export function SiteView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Site {id}</h1>
      <div className="rounded-lg border border-dashed border-neutral-300 p-10 text-center text-neutral-500">
        Site detail goes here.
      </div>
    </section>
  );
}
