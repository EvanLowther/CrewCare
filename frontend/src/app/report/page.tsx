import { ReportFormLoader } from "@/components/ReportFormLoader";
import { PageHeader } from "@/components/ui";

// Owner: Person B. Phone-first crew hazard report: photo, live GPS + draggable pin, type, severity, note.
export default function ReportPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Report a hazard" subtitle="Snap a photo, pin the spot, and share it with every crew nearby." />
      <ReportFormLoader />
    </div>
  );
}
