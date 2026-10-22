export type ResearchMetadata = {
  idea: string;
  notes: string;
  tags: string[];
  is_favorite?: boolean;
  updated_at?: string;
};
export type LibraryStrategy = {
  name: string;
  revision?: string;
  parameter_revision?: string;
  modified?: number;
  timeframe?: string;
  can_short?: boolean;
  protected?: boolean;
  invalid?: boolean;
  research?: ResearchMetadata;
};
export type LibraryRun = {
  id: string;
  strategy: string;
  revision: string;
  status: string;
  created_at: string;
  settings: Record<string, unknown>;
  preset?: StrategyPreset;
  summary?: {
    total_trades?: number;
    profit_total_abs?: number;
    profit_total?: number;
    max_drawdown_account?: number;
  };
};
export type StrategyPreset = {
  id: string;
  label: string;
  strategy: string;
  revision: string;
  schema_revision: string;
  parameter_revision: string;
  native_sha256: string;
  values: Record<string, string | number | boolean | null>;
  created_at: string;
  valid?: boolean;
};

/** Only completed archived runs supply metrics; never choose the most profitable result. */
export function latestLibraryRuns(runs: LibraryRun[]): Map<string, LibraryRun> {
  const latest = new Map<string, LibraryRun>();
  for (const run of runs) {
    if (run.status !== 'success') continue;
    const previous = latest.get(run.strategy);
    if (!previous || Date.parse(run.created_at) > Date.parse(previous.created_at))
      latest.set(run.strategy, run);
  }
  return latest;
}

export function libraryMatches(item: LibraryStrategy, query: string): boolean {
  const text = [item.name, item.research?.idea, ...(item.research?.tags ?? [])]
    .join(' ')
    .toLocaleLowerCase();
  return query
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .every((word) => text.includes(word));
}

export function libraryUpdated(item: LibraryStrategy): number {
  return Math.max((item.modified ?? 0) * 1000, Date.parse(item.research?.updated_at ?? '') || 0);
}
