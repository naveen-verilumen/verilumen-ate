import { formatTestLabel } from "../services/formatTestLabel";
import type { TestCatalogEntry } from "../types/api";

interface Props {
  catalog?: TestCatalogEntry[];
}

const ROWS: ReadonlyArray<{ testId: string; meaning: string; checks: string }> = [
  {
    testId: "T001",
    meaning: "Continuity check",
    checks: "Whether an electrical path/pin connection is actually connected",
  },
  {
    testId: "T002",
    meaning: "Open-circuit test",
    checks: "Whether a required connection is broken/disconnected",
  },
  {
    testId: "T003",
    meaning: "Short-circuit test",
    checks: "Whether two nodes that should be separate are unintentionally connected",
  },
  {
    testId: "T004",
    meaning: "Contact quality test",
    checks: "Whether the probe/device contact is electrically good enough for reliable measurement",
  },
  {
    testId: "T005",
    meaning: "Quiescent supply current test",
    checks: "Whether the chip draws abnormal current while in a quiescent state",
  },
  {
    testId: "T006",
    meaning: "Minimum operating voltage test",
    checks: "The lowest supply voltage at which the chip still operates correctly",
  },
  {
    testId: "T007",
    meaning: "Maximum operating voltage test",
    checks: "Whether the device operates correctly/safely at the specified upper voltage condition",
  },
  {
    testId: "T008",
    meaning: "Leakage-current test",
    checks: "Whether unwanted current flows through/off the device when it should be very small",
  },
  {
    testId: "T009",
    meaning: "Functional test",
    checks: "Whether the chip performs its intended logical/function behavior",
  },
  {
    testId: "T010",
    meaning: "Scan test",
    checks: "Whether internal scan chains/flip-flops can be shifted and observed correctly",
  },
];

const NOTE =
  "These are V2 synthetic test-slot definitions used for dashboard interpretation; they do not represent a complete real-world ATE test program.";

export function TestReference({ catalog }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Test reference">
      <details>
        <summary className="cursor-pointer select-none text-sm font-semibold uppercase tracking-wide text-slate-500">
          Test Reference
        </summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm text-slate-700">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4 font-medium">Test</th>
                <th className="py-2 pr-4 font-medium">What it means</th>
                <th className="py-2 font-medium">What it checks</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => {
                const label = formatTestLabel(row.testId, catalog);
                const slot = label.includes("—") ? label.split("—").pop()?.trim() ?? "" : "";
                return (
                  <tr key={row.testId} className="border-b border-slate-100 align-top">
                    <td className="whitespace-nowrap py-2 pr-4">
                      <div className="font-medium text-slate-900">{row.testId}</div>
                      <div className="text-xs tracking-wide text-slate-500">{slot}</div>
                    </td>
                    <td className="py-2 pr-4">{row.meaning}</td>
                    <td className="py-2">{row.checks}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500">{NOTE}</p>
      </details>
    </section>
  );
}
