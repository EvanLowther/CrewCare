import { PageHeader } from "@/components/ui";
import { AdminView } from "./AdminView";

// Owner: Person B. Admins: everyone who has signed in, their roles, and adding people to any site.
export default function AdminPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Admin" subtitle="Roles and site assignments for everyone who has signed in." />
      <AdminView />
    </div>
  );
}
