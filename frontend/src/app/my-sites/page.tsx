import { Suspense } from "react";
import { MySitesView } from "./MySitesView";
import { PageBody } from "@/components/ui";

// Owner: Person B. The sites you're on; pick one to see its crew reports (active, then past). Managers also manage
// the site and resolve reports here. ?site=<id> opens a site, so the browser's back button returns to the list.
export default function MySitesPage(props: PageProps<"/my-sites">) {
  return (
    <PageBody>
      <Suspense fallback={<p className="text-sm text-muted">Loading your sites…</p>}>
        <SiteParam searchParams={props.searchParams} />
      </Suspense>
    </PageBody>
  );
}

async function SiteParam({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { site } = await searchParams;
  const id = typeof site === "string" && /^\d+$/.test(site) ? Number(site) : null;
  return <MySitesView siteId={id} />;
}
