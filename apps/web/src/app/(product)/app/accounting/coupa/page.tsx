import { AccountingSystemPage } from "@/components/accounting/accounting-system-page";

export default function CoupaPage() {
  return (
    <AccountingSystemPage
      config={{
        system: "coupa",
        name: "Coupa",
        section: "Export",
        category: "Procurement",
        description:
          "Prepare a structured invoice package that can be handed to Coupa import or middleware workflows.",
        status: "export-ready",
        connection: "Export package",
        postingObject: "Invoice payload",
        masterData: "Suppliers + account codes",
        direction: "Inbound AP",
        primaryAction: "Download package",
        checklist: [
          "Normalize supplier, PO, tax, currency, and line fields.",
          "Map extracted categories to the client Coupa account structure.",
          "Generate import-ready CSV or JSON package.",
          "Store package evidence in the audit trail.",
        ],
        notes: [
          "Export-first flow is appropriate before API credentials are available.",
          "Client import templates should be uploaded per workspace.",
          "No industry-specific categories are hardcoded.",
        ],
      }}
    />
  );
}
