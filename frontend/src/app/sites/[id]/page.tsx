import { Suspense } from "react";
import type { Scorer } from "@/lib/api";
import { SiteView } from "./SiteView";

// Owner: Person B. Params are runtime data in Next 16: read them in a server component inside
// <Suspense> and hand the client plain values (passing the promise itself never resolved on the client).
export default function SitePage(props: PageProps<"/sites/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading site…</p>}>
      <SiteLoader params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}

async function SiteLoader({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  // ?model=rules (Real-time) or ml (Predictive), carried over from the dashboard's switch; default Predictive.
  const model: Scorer = query.model === "rules" ? "rules" : "ml";
  return <SiteView id={id} initialModel={model} />;
}
