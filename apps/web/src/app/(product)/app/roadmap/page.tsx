import { Rocket } from "lucide-react";

import { ContentCard } from "@/components/dashboard/content-card";
import { PageHeader } from "@/components/dashboard/page-header";

export default function RoadmapPage() {
  const milestones = [
    {
      title: "Reliable posting core",
      status: "Current",
      items: [
        "QuickBooks pilot",
        "Tally pilot",
        "Zoho Books adapter",
        "Auth boundary",
      ],
    },
    {
      title: "React operating console",
      status: "In progress",
      items: [
        "Queue parity",
        "ERP pages",
        "History",
        "Analytics",
        "Exceptions",
      ],
    },
    {
      title: "AI extraction layer",
      status: "Next",
      items: [
        "OCR fallback",
        "Field evidence",
        "Exception explanations",
        "Suggested corrections",
      ],
    },
    {
      title: "Client scale",
      status: "Future",
      items: [
        "Email intake",
        "Mobile approval",
        "Vendor portal",
        "Production deployment",
      ],
    },
  ];

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Roadmap"
        section="Build plan"
        description="The product path from demo-proven invoice posting to a scalable AP automation platform."
      />
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <ContentCard
          title="Milestone board"
          subtitle="Focused on dependability first, then wow features after posting is safe."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {milestones.map((milestone) => (
              <article
                key={milestone.title}
                className="rounded-2xl border border-line bg-canvas p-5"
              >
                <div className="flex items-center justify-between gap-3">
                  <Rocket className="text-cyan-ink" size={19} />
                  <span className="rounded-full border border-line bg-surface px-3 py-1 text-xs font-semibold text-ink-secondary">
                    {milestone.status}
                  </span>
                </div>
                <h2 className="mt-5 text-base font-semibold text-ink">
                  {milestone.title}
                </h2>
                <ul className="mt-4 space-y-3">
                  {milestone.items.map((item) => (
                    <li
                      key={item}
                      className="text-sm font-semibold text-ink-secondary"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </ContentCard>
      </main>
    </div>
  );
}
