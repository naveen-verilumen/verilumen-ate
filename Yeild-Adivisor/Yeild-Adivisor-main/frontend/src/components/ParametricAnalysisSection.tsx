import React, { useState } from 'react';
import type {
  ParametricAnalysisReport,
  ParametricAnalysisResult,
} from '../types/api';

interface ParametricAnalysisSectionProps {
  report?: ParametricAnalysisReport | null;
  loading?: boolean;
  error?: string | null;
  selectedLotId?: string | null;
}

export const ParametricAnalysisSection: React.FC<ParametricAnalysisSectionProps> = ({
  report,
  loading = false,
  error = null,
  selectedLotId,
}) => {
  const [selectedParam, setSelectedParam] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 my-6 animate-pulse" data-testid="parametric-loading">
        <div className="h-6 bg-slate-200 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-slate-100 rounded w-2/3 mb-6"></div>
        <div className="h-32 bg-slate-100 rounded"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-red-200 p-6 my-6" data-testid="parametric-error">
        <div className="flex items-center space-x-2 text-red-600 mb-2">
          <span className="font-semibold text-lg">Parametric Analysis Unavailable</span>
        </div>
        <p className="text-sm text-red-700">{error}</p>
      </div>
    );
  }

  if (!report || !report.results || report.results.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 my-6 text-center text-slate-500" data-testid="parametric-empty">
        No parametric analysis data available for this dataset.
      </div>
    );
  }

  // Determine active parameter
  const activeParamName =
    selectedParam ||
    report.results.find((r) => r.candidate_threshold?.status === 'INVESTIGATION_CANDIDATE_ONLY')
      ?.parameter_name ||
    report.results[0]?.parameter_name;

  const activeResult: ParametricAnalysisResult | undefined = report.results.find(
    (r) => r.parameter_name === activeParamName
  );

  const formatNum = (val: number | null | undefined, decimals = 4): string => {
    if (val === null || val === undefined) return '—';
    return Number(val).toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: decimals,
    });
  };

  const formatDirection = (direction: string | null | undefined): string => {
    if (direction === 'UPPER_BOUND') return '> ';
    if (direction === 'LOWER_BOUND') return '< ';
    if (direction === 'BAND') return '± ';
    return '';
  };

  const getBoundaryComparison = (result: ParametricAnalysisResult): string => {
    if (!result.candidate_threshold || result.candidate_threshold.candidate_value == null) {
      return 'No candidate boundary identified to compare against passing distribution.';
    }
    if (!result.pass_distribution || !result.pass_distribution.available) {
      return 'Passing-die distribution data is unavailable for comparison.';
    }

    const val = result.candidate_threshold.candidate_value;
    const pMin = result.pass_distribution.min;
    const pMax = result.pass_distribution.max;

    if (pMax != null && val > pMax) {
      return 'The candidate boundary is above all observed passing measurements.';
    }
    if (pMin != null && val < pMin) {
      return 'The candidate boundary is below all observed passing measurements.';
    }
    return 'The candidate boundary falls within the observed passing-die range.';
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 my-6" data-testid="parametric-analysis-section">
      {/* Section Header */}
      <h2 className="text-xl font-bold text-slate-900 mb-4">
        Parametric Threshold &amp; Distribution Analysis
      </h2>

      {/* Main Parameter Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm text-slate-600 border border-slate-200 rounded-lg overflow-hidden" data-testid="parameters-table">
          <thead className="bg-slate-50 text-xs font-semibold text-slate-700 uppercase tracking-wider border-b border-slate-200">
            <tr>
              <th className="py-3 px-4">Parameter</th>
              <th className="py-3 px-4">Target Failure</th>
              <th className="py-3 px-4 text-right">Target Dies</th>
              <th className="py-3 px-4">Candidate Boundary</th>
              <th className="py-3 px-4 text-center">Status</th>
              <th className="py-3 px-4 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {report.results.map((res) => {
              const isSelected = res.parameter_name === activeParamName;
              const hasCandidate =
                res.candidate_threshold?.status === 'INVESTIGATION_CANDIDATE_ONLY' &&
                res.candidate_threshold?.candidate_value != null;
              return (
                <tr
                  key={res.parameter_name}
                  onClick={() => setSelectedParam(res.parameter_name)}
                  className={`cursor-pointer transition-colors ${
                    isSelected ? 'bg-indigo-50/70 font-medium' : 'hover:bg-slate-50'
                  }`}
                  data-testid={`param-row-${res.parameter_name}`}
                >
                  <td className="py-3 px-4 font-mono font-bold text-slate-800">
                    {res.parameter_name} ({res.unit})
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-700">
                    {res.target_failure_code || '—'}
                  </td>
                  <td className="py-3 px-4 text-right font-mono text-xs text-slate-700">
                    {res.data_quality.target_failure_code_count > 0 ? (
                      `${res.data_quality.target_failure_code_count.toLocaleString()} dies`
                    ) : (
                      '0 dies'
                    )}
                  </td>
                  <td className="py-3 px-4 font-mono text-xs">
                    {hasCandidate && res.candidate_threshold ? (
                      <span className="text-indigo-700 font-semibold" data-testid={`candidate-boundary-${res.parameter_name}`}>
                        {formatDirection(res.candidate_threshold.direction)}
                        {formatNum(res.candidate_threshold.candidate_value)} {res.unit}
                      </span>
                    ) : (
                      <span className="text-slate-400">No reliable candidate boundary identified.</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-center">
                    {hasCandidate ? (
                      <span
                        className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300"
                        data-testid="status-investigate"
                      >
                        Investigate
                      </span>
                    ) : (
                      <span
                        className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200"
                        data-testid="status-more-evidence"
                      >
                        More evidence needed
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-center text-xs">
                    <button
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                        isSelected
                          ? 'bg-indigo-600 text-white shadow-sm'
                          : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                      }`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedParam(res.parameter_name);
                      }}
                    >
                      {isSelected ? 'Viewing' : 'Inspect'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Simplified Parameter Detail View */}
      {activeResult && (
        <div className="mt-6 pt-5 border-t border-slate-200 space-y-4" data-testid="param-detail-section">
          {/* Header: Parameter Name & Unit + Scope */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wider block">
                Parameter Detail
              </span>
              <h3 className="text-lg font-bold text-slate-900 font-mono" data-testid="selected-param-title">
                {activeResult.parameter_name} ({activeResult.unit})
              </h3>
            </div>
            {selectedLotId ? (
              <span className="self-start sm:self-auto px-2.5 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                Scope: Lot {selectedLotId}
              </span>
            ) : (
              <span className="self-start sm:self-auto px-2.5 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                Scope: All Lots
              </span>
            )}
          </div>

          {/* Candidate Boundary & Passing-Die Statistics (Compact Grid) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Candidate Boundary */}
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200" data-testid="candidate-boundary-card">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                Candidate Boundary
              </span>
              {activeResult.candidate_threshold && activeResult.candidate_threshold.candidate_value != null ? (
                <div className="text-lg font-bold font-mono text-indigo-700" data-testid="detail-candidate-callout">
                  {formatDirection(activeResult.candidate_threshold.direction)}
                  {formatNum(activeResult.candidate_threshold.candidate_value)} {activeResult.unit}
                </div>
              ) : (
                <div className="text-sm text-slate-500 italic">
                  No reliable candidate boundary identified.
                </div>
              )}
              {/* Boundary Comparison (one short sentence) */}
              <p className="text-xs text-slate-600 mt-2" data-testid="boundary-comparison-text">
                {getBoundaryComparison(activeResult)}
              </p>
            </div>

            {/* Passing-Die Statistics */}
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200" data-testid="passing-stats-card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Passing-Die Statistics
                </span>
                {activeResult.pass_distribution?.available && (
                  <span className="text-[11px] font-mono text-slate-500">
                    n = {activeResult.pass_distribution.count.toLocaleString()}
                  </span>
                )}
              </div>
              {activeResult.pass_distribution && activeResult.pass_distribution.available ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                  <div className="bg-white p-2 rounded border border-slate-200">
                    <span className="text-slate-400 block font-sans text-[10px] uppercase">Mean</span>
                    <span className="font-semibold text-slate-800" data-testid="pass-mean">
                      {formatNum(activeResult.pass_distribution.mean)} {activeResult.unit}
                    </span>
                  </div>
                  <div className="bg-white p-2 rounded border border-slate-200">
                    <span className="text-slate-400 block font-sans text-[10px] uppercase">Median</span>
                    <span className="font-semibold text-slate-800" data-testid="pass-median">
                      {formatNum(activeResult.pass_distribution.median)} {activeResult.unit}
                    </span>
                  </div>
                  <div className="bg-white p-2 rounded border border-slate-200">
                    <span className="text-slate-400 block font-sans text-[10px] uppercase">Min</span>
                    <span className="font-semibold text-slate-800" data-testid="pass-min">
                      {formatNum(activeResult.pass_distribution.min)} {activeResult.unit}
                    </span>
                  </div>
                  <div className="bg-white p-2 rounded border border-slate-200">
                    <span className="text-slate-400 block font-sans text-[10px] uppercase">Max</span>
                    <span className="font-semibold text-slate-800" data-testid="pass-max">
                      {formatNum(activeResult.pass_distribution.max)} {activeResult.unit}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-slate-500 italic py-2">
                  Passing-die statistics unavailable.
                </div>
              )}
            </div>
          </div>

          {/* Recommended Next Steps (no more than 3 concise actions) */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200" data-testid="recommended-steps-card">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-2">
              Recommended Next Steps
            </span>
            <ul className="text-xs text-slate-700 space-y-1.5 list-disc list-inside">
              <li>Verify test setup, probe card contact integrity, and measurement repeatability.</li>
              <li>Investigate physical root causes, including defect density, process layer shifts, and tool variation.</li>
              <li>Compare the candidate boundary against original product specifications before evaluating test limits.</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};

export default ParametricAnalysisSection;
