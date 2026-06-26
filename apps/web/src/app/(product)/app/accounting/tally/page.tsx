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
          "Use Generic / manual setup for normal ledger vouchers.",
          "Use NEEL ENTERPRISE - PTA item invoice for the confirmed PTA SWEEP, IGST, TCS, and round-off flow.",
        ],
        notes: [
          "Live Tally posting has been proven with client data.",
          "The Neel profile uses company NEEL ENTERPRISE, voucher type Purchase, stock item PTA SWEEP, HSN 29173600, GST 18%, and Tally unit KGS.",
          "Client profiles keep exact ledger and stock item names separate so one client's Tally setup does not affect another client.",
          "Ledger and stock item names must match Tally exactly to avoid import failures.",
        ],
      }}
    />
  );
}
