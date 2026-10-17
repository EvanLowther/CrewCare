// Owner: Person B. Hours 12-15: phone-friendly form. Photo (<input type="file" accept="image/*"
// capture="environment">), current GPS via navigator.geolocation, hazard type, severity, note.
// Submit with api.createReport().
export default function ReportPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Report a hazard</h1>
      <div className="rounded-lg border border-dashed border-neutral-300 p-10 text-center text-neutral-500">
        Crew report form goes here.
      </div>
    </section>
  );
}
