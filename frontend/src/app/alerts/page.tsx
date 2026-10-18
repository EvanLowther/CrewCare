import { AlertsView } from "./AlertsView";
import { PageBody } from "@/components/ui";

// Owner: Person B. Every active alert across all sites, refreshed every 10 s.
export default function AlertsPage() {
  return (
    <PageBody>
      <AlertsView />
    </PageBody>
  );
}
