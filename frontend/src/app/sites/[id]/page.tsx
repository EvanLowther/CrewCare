import { Suspense } from "react";
import { SiteView } from "./SiteView";

// Owner: Person B. Params are runtime data in Next 16: read them in a server component inside
// <Suspense> and hand the client a plain id (passing the promise itself never resolved on the client).
export default function SitePage(props: PageProps<"/sites/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading site…</p>}>
      <SiteLoader params={props.params} />
    </Suspense>
  );
}

async function SiteLoader({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SiteView id={id} />;
}
