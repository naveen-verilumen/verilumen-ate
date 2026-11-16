import type { ReactNode } from "react";

interface Props {
  title?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}

export function Expandable({ title = "Details", children, defaultOpen = false }: Props) {
  return (
    <details className="mt-3 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm" open={defaultOpen}>
      <summary className="cursor-pointer select-none text-slate-600">{title}</summary>
      <div className="mt-2 text-slate-800">{children}</div>
    </details>
  );
}
