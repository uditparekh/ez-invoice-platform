import { AccountingSystemPage } from "@/components/accounting/accounting-system-page";

export default function ZohoBooksPage() {
  return (
    <AccountingSystemPage
      config={{
        system: "zoho_books",
        name: "Zoho Books",
        section: "Integration",
        category: "Cloud accounting",
        description:
          "Prepare vendor bills for Zoho Books with contact matching, tax treatment, and item/account mapping.",
        status: "configured",
        connection: "OAuth API",
        postingObject: "Vendor Bill",
        masterData: "Contacts + taxes",
        direction: "Inbound AP",
        primaryAction: "Connect Zoho",
        checklist: [
          "Connect the client Zoho Books organization.",
          "Sync contacts, chart of accounts, tax rates, and currencies.",
          "Map invoice categories to Zoho expense or item accounts.",
          "Post approved supplier bills with source PDF references.",
        ],
        notes: [
          "Adapter logic is in place for the next integration test.",
          "Indian GST handling should use client-provided tax names.",
          "Multi-organization support should be verified before demos.",
        ],
      }}
    />
  );
}
