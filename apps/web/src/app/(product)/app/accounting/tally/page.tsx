import { AccountingSystemPage } from "@/components/accounting/accounting-system-page";

export default function TallyPage() {
  return (
    <AccountingSystemPage
      config={{
        system: "tally",
        name: "Tally",
        section: "Integration",
        category: "Desktop accounting",
        description:
          "Post approved purchase bills to TallyPrime through a secure local connector running beside the client company data.",
        status: "pilot-ready",
        connection: "Local XML bridge",
        postingObject: "Voucher or item invoice",
        masterData: "Client profiles",
        direction: "Inbound AP",
        primaryAction: "Test connector",
        checklist: [
          "Run the local connector on the same Windows machine as TallyPrime.",
          "Verify Tally HTTP/XML access on port 9000.",
          "Choose the client setup profile before posting or exporting XML.",
          "Use accounting voucher mode for ledger-only purchase entries.",
          "Use item invoice mode when the client needs Tally stock items, HSN/SAC, GST ledgers, and inventory quantities.",
        ],
        notes: [
          "Live Tally posting has been proven through the local connector flow.",
          "Client profiles keep company names, voucher types, ledgers, tax ledgers, stock items, HSN/SAC, and units separate for each workspace.",
          "The GST item template is only a starter; users must fill exact Tally ledger and stock item names before posting.",
          "Ledger and stock item names must match Tally exactly to avoid import failures.",
        ],
      }}
    />
  );
}
