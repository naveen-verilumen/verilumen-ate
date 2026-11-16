import { useEffect, useMemo, useState } from "react";
import { formatCount, formatRate } from "../services/format";
import { formatTestLabel } from "../services/formatTestLabel";
import type {
  TestCatalogEntry,
  WaferMapDie,
  WaferMapResponse,
} from "../types/api";

interface Props {
  data: WaferMapResponse | null | undefined;
  catalog: TestCatalogEntry[] | undefined;
  selectedLotId?: string | null;
}

interface FailureGroup {
  testId: string;
  failureCode: string;
  count: number;
}

interface PassFailSummary {
  n: number;
  passed: number;
  failed: number;
  fpy: number | null;
}

function dieKey(die: WaferMapDie): string {
  return `${die.lot_id}|${die.wafer_id}|${die.die_id}`;
}

function waferDies(dies: WaferMapDie[], lotId: string, waferId: string): WaferMapDie[] {
  return dies.filter((die) => die.lot_id === lotId && die.wafer_id === waferId);
}

function summarize(dies: WaferMapDie[]): PassFailSummary {
  const n = dies.length;
  const passed = dies.filter((die) => die.first_pass_result === "PASS").length;
  const failed = dies.filter((die) => die.first_pass_result === "FAIL").length;
  return { n, passed, failed, fpy: n > 0 ? passed / n : null };
}

function failureGroups(dies: WaferMapDie[]): FailureGroup[] {
  const counts = new Map<string, FailureGroup>();
  for (const die of dies) {
    if (die.first_pass_result !== "FAIL" || !die.failed_test_id) {
      continue;
    }
    const key = `${die.failed_test_id}|${die.failure_code ?? ""}`;
    const existing = counts.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      counts.set(key, {
        testId: die.failed_test_id,
        failureCode: die.failure_code ?? "",
        count: 1,
      });
    }
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.testId.localeCompare(b.testId));
}

function tooltipFor(die: WaferMapDie, catalog: TestCatalogEntry[] | undefined): string {
  if (die.first_pass_result === "PASS") {
    return `PASS\nDie ${die.die_id}\nPosition X: ${die.x ?? "—"}\nPosition Y: ${die.y ?? "—"}`;
  }
  const test = die.failed_test_id ? formatTestLabel(die.failed_test_id, catalog) : "Unavailable";
  const reason = die.failure_code ? `\nReason: ${die.failure_code}` : "";
  return `FAIL\nDie ${die.die_id}\n${test}${reason}`;
}

function StatRow({ label, stats }: { label: string; stats: PassFailSummary }) {
  return (
    <div>
      <p className="text-sm font-medium text-slate-800">{label}</p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-700 sm:grid-cols-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">Dies</div>
          <div className="font-mono font-semibold">{formatCount(stats.n)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">Passed</div>
          <div className="font-mono font-semibold">{formatCount(stats.passed)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">Failed</div>
          <div className="font-mono font-semibold">{formatCount(stats.failed)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">FPY</div>
          <div className="font-mono font-semibold">{formatRate(stats.fpy)}</div>
        </div>
      </div>
    </div>
  );
}

export function WaferMap({ data, catalog, selectedLotId }: Props) {
  const lots = data?.lots ?? [];
  const requestedLotId =
    selectedLotId && lots.some((lot) => lot.lot_id === selectedLotId) ? selectedLotId : (lots[0]?.lot_id ?? "");
  const [waferId, setWaferId] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const effectiveLotId = lots.some((lot) => lot.lot_id === requestedLotId) ? requestedLotId : (lots[0]?.lot_id ?? "");
  const selectedLot = lots.find((lot) => lot.lot_id === effectiveLotId) ?? null;
  const wafers = selectedLot?.wafers ?? [];
  const activeWaferId = wafers.includes(waferId) ? waferId : (wafers[0] ?? "");

  useEffect(() => {
    setWaferId("");
    setSelectedKey(null);
  }, [effectiveLotId]);

  const lotDies = useMemo(
    () => (data && selectedLot ? data.dies.filter((die) => die.lot_id === selectedLot.lot_id) : []),
    [data, selectedLot],
  );
  const dies = useMemo(
    () => (data && selectedLot ? waferDies(data.dies, selectedLot.lot_id, activeWaferId) : []),
    [data, selectedLot, activeWaferId],
  );
  const selected = dies.find((die) => dieKey(die) === selectedKey) ?? null;

  const lotStats = summarize(lotDies);
  const waferStats = summarize(dies);
  const xs = dies.map((die) => die.x).filter((value): value is number => value !== null);
  const ys = dies.map((die) => die.y).filter((value): value is number => value !== null);
  const minX = xs.length ? Math.min(...xs) : 1;
  const maxX = xs.length ? Math.max(...xs) : 10;
  const minY = ys.length ? Math.min(...ys) : 1;
  const maxY = ys.length ? Math.max(...ys) : 10;
  const byCoord = new Map(dies.map((die) => [`${die.x},${die.y}`, die]));
  const summary = failureGroups(dies);
  const lotLabel = selectedLot?.display_name ?? "Unavailable";

  if (!data) {
    return null;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Wafer map">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Wafer map</h2>
      <div className="mt-3 flex flex-col gap-3">
        <p className="text-sm text-slate-600">
          Lot <span className="font-medium text-slate-800">{lotLabel}</span>
        </p>
        <div>
          <p className="text-sm text-slate-600">Wafer</p>
          <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Wafer map wafer">
            {wafers.map((id) => {
              const selectedWafer = id === activeWaferId;
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={selectedWafer}
                  aria-label={`Wafer ${id}`}
                  className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                    selectedWafer
                      ? "bg-slate-900 text-white"
                      : "border border-slate-300 bg-white text-slate-700 hover:border-slate-400"
                  }`}
                  onClick={() => {
                    setWaferId(id);
                    setSelectedKey(null);
                  }}
                >
                  {id}
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="mt-4 space-y-4">
        <StatRow label={lotLabel} stats={lotStats} />
        <StatRow label={`Selected wafer: ${activeWaferId || "—"}`} stats={waferStats} />
      </div>
      <p className="mt-3 text-sm font-medium uppercase tracking-wide text-slate-800">
        {lotLabel} · WAFER {activeWaferId || "—"}
      </p>
      <p className="mt-3 text-sm text-slate-600">
        Each square represents one die. Select a wafer to view its dies, then select a die to see its first-pass test
        result and failure reason.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.4fr)_20rem]">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Wafer die map</h3>
          <div className="mt-3 flex gap-3">
            <div className="flex flex-col items-center justify-between py-8 text-[10px] uppercase tracking-wide text-slate-400">
              <span>Y</span>
              <span>↑</span>
            </div>
            <div className="min-w-0 flex-1">
              <div
                className="mx-auto grid max-w-xl gap-1.5"
                style={{ gridTemplateColumns: `repeat(${maxX - minX + 1}, minmax(0, 1fr))` }}
                aria-label="Wafer die map"
              >
                {Array.from({ length: maxY - minY + 1 }, (_, row) => maxY - row).flatMap((y) =>
                  Array.from({ length: maxX - minX + 1 }, (_, col) => {
                    const x = minX + col;
                    const die = byCoord.get(`${x},${y}`);
                    if (!die) {
                      return <div key={`empty-${x}-${y}`} className="aspect-square min-h-8 rounded-sm bg-slate-100" />;
                    }
                    const selectedDie = dieKey(die) === selectedKey;
                    const passedDie = die.first_pass_result === "PASS";
                    return (
                      <button
                        key={dieKey(die)}
                        type="button"
                        title={tooltipFor(die, catalog)}
                        aria-label={`Die ${die.die_id} ${die.first_pass_result} X ${die.x} Y ${die.y}`}
                        aria-pressed={selectedDie}
                        className={`aspect-square min-h-8 rounded-sm ${
                          passedDie ? "bg-emerald-500 hover:bg-emerald-600" : "bg-rose-500 hover:bg-rose-600"
                        } ${selectedDie ? "ring-2 ring-slate-900 ring-offset-1" : ""}`}
                        onClick={() => setSelectedKey(dieKey(die))}
                      />
                    );
                  }),
                )}
              </div>
              <p className="mt-2 text-center text-[10px] uppercase tracking-wide text-slate-400">→ X</p>
            </div>
          </div>
          <ul className="mt-3 flex flex-wrap gap-4 text-xs text-slate-600">
            <li className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-sm bg-emerald-500" /> PASS
            </li>
            <li className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-sm bg-rose-500" /> FAIL
            </li>
            <li className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-sm bg-emerald-500 ring-2 ring-slate-900 ring-offset-1" />{" "}
              SELECTED
            </li>
          </ul>
        </div>
        <div className="space-y-4">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">First-pass failure summary</h3>
            {summary.length === 0 ? (
              <p className="mt-2 text-sm text-slate-600">No first-pass failures on this wafer.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-sm text-slate-800">
                {summary.map((row) => (
                  <li key={`${row.testId}-${row.failureCode}`} className="rounded border border-slate-200 px-3 py-2">
                    <div className="font-medium">{formatTestLabel(row.testId, catalog)}</div>
                    <div className="text-slate-600">{row.failureCode || "Unavailable"}</div>
                    <div className="font-mono text-xs text-slate-600">{formatCount(row.count)} dies</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Selected die</h3>
            {selected ? (
              <dl className="mt-2 space-y-1 text-sm text-slate-800" data-testid="selected-die-panel">
                <div>
                  <dt className="text-xs uppercase text-slate-500">Die</dt>
                  <dd className="font-medium">{selected.die_id}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Position</dt>
                  <dd>
                    X: {selected.x ?? "—"}
                    <br />
                    Y: {selected.y ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Result</dt>
                  <dd>{selected.first_pass_result === "PASS" ? "Passed" : "Failed"}</dd>
                </div>
                {selected.first_pass_result === "PASS" ? (
                  <div>
                    <dt className="text-xs uppercase text-slate-500">First-pass result</dt>
                    <dd>Passed all tests</dd>
                  </div>
                ) : (
                  <>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Failed test</dt>
                      <dd>{selected.failed_test_id ? formatTestLabel(selected.failed_test_id, catalog) : "Unavailable"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">Failure reason</dt>
                      <dd>{selected.failure_code || "Unavailable"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase text-slate-500">First-pass result</dt>
                      <dd>Failed</dd>
                    </div>
                  </>
                )}
                {selected.retest_available ? (
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Retest</dt>
                    <dd>Retest available</dd>
                  </div>
                ) : null}
              </dl>
            ) : (
              <p className="mt-2 text-sm text-slate-600">Select a die on the map.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
