import { PageBody, PageHeader } from "@/components/ui";
import { NewSite } from "./NewSite";

// Owner: Person B. Managers create a private site; they become its manager and add their crew next.
export default function NewSitePage() {
  return (
    <PageBody>
      <div className="flex flex-col gap-6">
        <PageHeader title="New site" subtitle="A private site: only the people you add (and admins) can see it." />
        <NewSite />
      </div>
    </PageBody>
  );
}
