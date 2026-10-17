import { FileText } from "lucide-react";
import { Card, CardHeader, EmptyState, PageHeader } from "@/components/ui";

// Owner: Person B. Hours 19-21: tomorrow's briefing per site, plus a "Generate now" demo button
// (api.generateBriefings()). Data: api.briefings().
export default function BriefingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Briefings" subtitle="Next-day safety briefing for every site, sent at 6 PM local time." />
      <Card>
        <CardHeader title="Tomorrow's briefings" icon={FileText} />
        <EmptyState icon={FileText} title="Briefings arrive with the 6 PM job" detail="Each site gets a plain-English summary of tomorrow's heat, storms and hazards." />
      </Card>
    </div>
  );
}
