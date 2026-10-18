import { Suspense } from "react";
import { ManageSite } from "./ManageSite";
import { PageBody } from "@/components/ui";

// Owner: Person B. A site's managers edit it, choose who's on it, and (its creator) delete it.
export default function ManageSitePage(props: PageProps<"/sites/[id]/manage">) {
  return (
    <PageBody>
      <Suspense fallback={<p className="text-sm text-muted">Loading site…</p>}>
        <ManageLoader params={props.params} searchParams={props.searchParams} />
      </Suspense>
    </PageBody>
  );
}

async function ManageLoader({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <ManageSite id={Number(id)} isNew={query.new === "1"} />;
}
