// Owner: Person B. Hours 19-21: tomorrow's briefing per site, plus a "Generate now" demo button
// (api.generateBriefings()). Data: api.briefings().
export default function BriefingsPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Next-day safety briefings</h1>
      <div className="rounded-lg border border-dashed border-neutral-300 p-10 text-center text-neutral-500">
        Briefings go here.
      </div>
    </section>
  );
}
