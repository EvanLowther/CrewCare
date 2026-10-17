import { Suspense } from "react";
import { SiteView } from "./SiteView";

// Owner: Person B. Params are runtime data in Next 16, so they're read inside <Suspense>.
export default function SitePage(props: PageProps<"/sites/[id]">) {
  return (
    <Suspense fallback={<p className="text-neutral-500">Loading site…</p>}>
      <SiteView params={props.params} />
    </Suspense>
  );
}
