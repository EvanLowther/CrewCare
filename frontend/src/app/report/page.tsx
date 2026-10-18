import { Suspense } from "react";
import { ReportFormLoader } from "@/components/ReportFormLoader";
import { PageBody, PageHeader } from "@/components/ui";

// Owner: Person B. Phone-first crew hazard report: photo, live GPS + draggable pin, site, type, severity, note.
// ?site=<id> (from a site page's "Report hazard" button) preselects that site when you're near it.
export default function ReportPage(props: PageProps<"/report">) {
  return (
    <PageBody>
      <div className="flex flex-col gap-6">
        <PageHeader title="Report a hazard" subtitle="Snap a photo, pin the spot, and share it with your site's crew." />
        <Suspense fallback={<p className="text-sm text-muted">Loading report form…</p>}>
          <ReportLoader searchParams={props.searchParams} />
        </Suspense>
      </div>
    </PageBody>
  );
}

async function ReportLoader({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { site } = await searchParams;
  const id = typeof site === "string" && /^\d+$/.test(site) ? Number(site) : null;
  return <ReportFormLoader initialSiteId={id} />;
}
