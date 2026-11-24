import React from 'react';
import type { RiskLevel } from '../types';

const RISK_STYLES: Record<RiskLevel, string> = {
  CRITICAL: 'bg-red-100 text-red-800 border-red-200',
  HIGH: 'bg-orange-100 text-orange-800 border-orange-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  LOW: 'bg-blue-100 text-blue-800 border-blue-200',
  INFO: 'bg-sky-100 text-sky-800 border-sky-200',
  PASS: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

export const RiskBadge: React.FC<{ level: RiskLevel | null | undefined }> = ({ level }) => {
  if (!level) {
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">
        PENDING
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold border ${RISK_STYLES[level] ?? 'bg-slate-100 text-slate-700'}`}
    >
      {level}
    </span>
  );
};
