import { ApiStatus } from "@/components/ApiStatus";

// Owner: Person B. Hours 4-8: Leaflet map with risk-coloured pins + side list sorted by score.
// Data: api.sites() (SiteList, already sorted highest risk first). Poll api.alerts({ since }) every 10 s.
export default function DashboardPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Site risk dashboard</h1>
      <ApiStatus />
      <div className="rounded-lg border border-dashed border-neutral-300 p-10 text-center text-neutral-500">
        Map and ranked site list go here.
      </div>
    </section>
  );
}
