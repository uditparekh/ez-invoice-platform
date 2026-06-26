import { AccountingSystemPage } from "@/components/accounting/accounting-system-page";

export default function QuickBooksPage() {
  return (
    <AccountingSystemPage
      config={{
        system: "quickbooks",
        name: "QuickBooks",
        section: "Integration",
        category: "Cloud accounting",
        description:
          "Create supplier Bills in QuickBooks Online using client authorization, vendor matching, and saved account mappings.",
        status: "pilot-ready",
        connection: "OAuth API",
        postingObject: "Supplier Bill",
        masterData: "Vendors + accounts",
        direction: "Inbound AP",
        primaryAction: "Connect QuickBooks",
        checklist: [
          "Connect the client QuickBooks company through OAuth.",
          "Refresh chart of accounts and vendor masters.",
          "Map extracted line categories to expense accounts.",
          "Post approved invoices as supplier Bills with audit evidence.",
        ],
        notes: [
          "Sandbox posting has already been proven from the pilot.",
          "Each client workspace should own its own QuickBooks tokens.",
          "Universal categories are used; no industry-specific logic is required.",
        ],
      }}
    />
  );
}
