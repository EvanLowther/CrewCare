import { BriefingsView } from "./BriefingsView";
import { PageBody } from "@/components/ui";

// Owner: Person B. Tomorrow's (or today's) safety briefing per site, plus "Generate now" for admins.
export default function BriefingsPage() {
  return (
    <PageBody>
      <BriefingsView />
    </PageBody>
  );
}
