import { Camera, MapPin } from "lucide-react";
import { Card, CardHeader, EmptyState, PageHeader } from "@/components/ui";

// Owner: Person B. Hours 12-15: phone-friendly form. Photo (<input type="file" accept="image/*"
// capture="environment">), current GPS via navigator.geolocation, hazard type, severity, note.
// Submit with api.createReport().
export default function ReportPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Crew reports" subtitle="Snap a photo, pin the hazard, and share it with every crew nearby." />
      <Card>
        <CardHeader title="Report a hazard" icon={Camera} />
        <EmptyState icon={MapPin} title="Report form coming next" detail="Photo, GPS pin, hazard type and severity, posted to the map in seconds." />
      </Card>
    </div>
  );
}
