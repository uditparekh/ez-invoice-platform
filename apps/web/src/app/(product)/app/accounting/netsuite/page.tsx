import { AccountingSystemPage } from "@/components/accounting/accounting-system-page";

export default function NetSuitePage() {
  return (
    <AccountingSystemPage
      config={{
        system: "netsuite",
        name: "NetSuite",
        section: "Export",
        category: "ERP",
        description:
          "Prepare vendor bill payloads for NetSuite with subsidiary, vendor, tax, department, and account dimensions.",
        status: "export-ready",
        connection: "SuiteTalk or export",
        postingObject: "Vendor Bill",
        masterData: "Vendors + dimensions",
        direction: "Inbound AP",
        primaryAction: "Download package",
        checklist: [
          "Capture subsidiary, vendor, currency, tax, and department defaults.",
          "Map invoice lines to NetSuite accounts and classifications.",
          "Generate a clean vendor bill import package.",
          "Promote to SuiteTalk posting after client credentials are approved.",
        ],
        notes: [
          "NetSuite needs stronger master-data mapping than small-business tools.",
          "Subsidiary and department fields should be client-configurable.",
          "This page is ready for the export workflow milestone.",
        ],
      }}
    />
  );
}
