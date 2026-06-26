import { AccountingSystemPage } from "@/components/accounting/accounting-system-page";

export default function SapPage() {
  return (
    <AccountingSystemPage
      config={{
        system: "sap",
        name: "SAP",
        section: "Export",
        category: "Enterprise ERP",
        description:
          "Prepare SAP-ready invoice payloads with vendor, company code, tax code, cost center, and GL assignment.",
        status: "planned",
        connection: "BAPI, IDoc, or export",
        postingObject: "Vendor invoice",
        masterData: "Vendor + GL + tax code",
        direction: "Inbound AP",
        primaryAction: "Plan SAP mapping",
        checklist: [
          "Define company code, purchasing org, tax, and cost-center fields.",
          "Create workspace-specific GL and tax-code mapping rules.",
          "Generate an import-ready package for SAP validation.",
          "Add connector posting only after sandbox credentials are available.",
        ],
        notes: [
          "SAP should start with package validation, not blind live posting.",
          "Client master-data upload will be important for reliable demos.",
          "The universal invoice schema already supports the needed fields.",
        ],
      }}
    />
  );
}
