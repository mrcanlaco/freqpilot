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
  startup_candle_count?: number;
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
  optimization?: { id: string; epoch: number; spaces: string[]; loss: string; train_timerange: string; oos_timerange?: string };
  special_params?: Record<string, unknown>;
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

export function formatLibraryRunSummary(run?: LibraryRun, digits = 2) {
  const profit = run?.summary?.profit_total_abs;
  const trades = run?.summary?.total_trades;
  const hasProfit = typeof profit === 'number' && Number.isFinite(profit);
  const hasTrades = typeof trades === 'number' && Number.isFinite(trades);
  const profitText = hasProfit ? `${profit.toFixed(digits)} USDT` : '—';
  const signedProfitText = hasProfit ? `${profit >= 0 ? '+' : ''}${profit.toFixed(digits)} USDT` : '—';
  const tradesText = hasTrades ? `${trades} lệnh` : '— lệnh';
  return {
    hasProfit,
    hasTrades,
    profitText,
    signedProfitText,
    tradesText,
    contextText: `${profitText} · ${tradesText}`,
  };
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export type WalkForwardWindowRow = {
  index: number;
  train_timerange: string;
  test_timerange: string;
  status: string;
  train_profit: number | null;
  train_profit_abs: number | null;
  train_trades: number | null;
  baseline_profit_abs: number | null;
  baseline_trades: number | null;
  test_profit: number | null;
  test_profit_abs: number | null;
  test_trades: number | null;
  wfe: null;
  degradation: null;
};

export function mapWalkForwardWindowRow(w: Record<string, unknown>): WalkForwardWindowRow {
  const hyperopt = w.hyperopt as Record<string, unknown> | undefined;
  const bestEpoch =
    hyperopt?.status === 'success'
      ? (hyperopt.best_epoch as Record<string, unknown> | undefined)
      : undefined;
  const trainMetrics = bestEpoch?.metrics as Record<string, unknown> | undefined;
  const baselineSummary = (w.baseline as Record<string, unknown> | undefined)?.summary as
    | Record<string, unknown>
    | undefined;
  const candidateSummary = (w.candidate as Record<string, unknown> | undefined)?.summary as
    | Record<string, unknown>
    | undefined;

  return {
    index: finiteNumber(w.index) ?? 0,
    train_timerange: String(w.train_timerange ?? ''),
    test_timerange: String(w.oos_timerange ?? w.test_timerange ?? ''),
    status: String(w.status ?? ''),
    train_profit: finiteNumber(trainMetrics?.profit_total),
    train_profit_abs: finiteNumber(trainMetrics?.profit_total_abs),
    train_trades: finiteNumber(trainMetrics?.total_trades),
    baseline_profit_abs: finiteNumber(baselineSummary?.profit_total_abs),
    baseline_trades: finiteNumber(baselineSummary?.total_trades),
    test_profit: finiteNumber(candidateSummary?.profit_total),
    test_profit_abs: finiteNumber(candidateSummary?.profit_total_abs),
    test_trades: finiteNumber(candidateSummary?.total_trades),
    wfe: null,
    degradation: null,
  };
}

export type SensitivityAxisInput = {
  name: string;
  base: number;
  values: number[];
};

export type SensitivityCellInput = {
  index: number;
  parameters: Record<string, number>;
  fee: number;
  status: string;
  result: Record<string, unknown> | null;
  error?: string;
};

export type SensitivityPivotCol = {
  key: string;
  label: string;
  paramValue?: number;
  fee: number;
  isBase: boolean;
};

export type SensitivityPivotCell = {
  status: string;
  isBaseline: boolean;
  profitValue: number | null;
  profitText: string;
  tradesText: string;
  drawdownText: string;
  error?: string;
};

export function buildSensitivityPivot(job?: {
  axes?: SensitivityAxisInput[];
  cells?: SensitivityCellInput[];
}) {
  const axes = job?.axes ?? [];
  const cells = job?.cells ?? [];
  const rowAxis = axes[0] ?? { name: '', base: 0, values: [] };
  const secondAxis = axes[1];

  const fees: number[] = [];
  for (const c of cells) {
    if (
      typeof c.fee === 'number' &&
      Number.isFinite(c.fee) &&
      !fees.some((f) => Math.abs(f - c.fee) < 1e-12)
    ) {
      fees.push(c.fee);
    }
  }
  const feeList = fees.length ? fees : [0];

  const colItems: SensitivityPivotCol[] = [];
  if (secondAxis && feeList.length <= 1) {
    const fee = feeList[0] ?? 0;
    for (const val of secondAxis.values) {
      colItems.push({
        key: `${val}`,
        label: `${val}`,
        paramValue: val,
        fee,
        isBase: Math.abs(val - secondAxis.base) < 1e-9,
      });
    }
  } else if (secondAxis) {
    for (const val of secondAxis.values) {
      feeList.forEach((fee, fIdx) => {
        const feeText = `${Number((fee * 100).toFixed(4))}%`;
        colItems.push({
          key: `${val}::${feeText}`,
          label: `${val} · ${feeText}`,
          paramValue: val,
          fee,
          isBase: Math.abs(val - secondAxis.base) < 1e-9 && fIdx === 0,
        });
      });
    }
  } else {
    feeList.forEach((fee, fIdx) => {
      const feeText = `${Number((fee * 100).toFixed(4))}%`;
      colItems.push({
        key: feeText,
        label: feeText,
        fee,
        isBase: fIdx === 0,
      });
    });
  }

  const colAxisName = secondAxis
    ? feeList.length > 1
      ? `${secondAxis.name} · Phí`
      : secondAxis.name
    : 'Phí mỗi chiều';

  const matrix: SensitivityPivotCell[][] = rowAxis.values.map((rowVal) => {
    const isRowBase = Math.abs(rowVal - rowAxis.base) < 1e-9;
    return colItems.map((col) => {
      const cell = cells.find((c) => {
        const rMatch = Math.abs((c.parameters?.[rowAxis.name] ?? Number.NaN) - rowVal) < 1e-9;
        if (!rMatch) return false;
        if (secondAxis) {
          const cMatch =
            Math.abs((c.parameters?.[secondAxis.name] ?? Number.NaN) - (col.paramValue ?? Number.NaN)) <
            1e-9;
          if (!cMatch) return false;
        }
        if (feeList.length > 1) {
          return Math.abs(c.fee - col.fee) < 1e-12;
        }
        return true;
      });

      const status = cell?.status ?? 'pending';
      const summary =
        status === 'success'
          ? (cell?.result?.summary as Record<string, unknown> | undefined)
          : undefined;
      const profit = finiteNumber(summary?.profit_total_abs);
      const trades = finiteNumber(summary?.total_trades);
      const drawdown = finiteNumber(summary?.max_drawdown_account);

      return {
        status,
        isBaseline: isRowBase && col.isBase,
        profitValue: profit,
        profitText: profit !== null ? `${profit.toFixed(2)} USDT` : '—',
        tradesText: trades !== null ? `${trades} lệnh` : '—',
        drawdownText: drawdown !== null ? `${(drawdown * 100).toFixed(2)}%` : '—',
        error: cell?.error,
      };
    });
  });

  return {
    rowAxis: {
      name: rowAxis.name,
      base: rowAxis.base,
      values: rowAxis.values,
    },
    colAxis: {
      name: colAxisName,
      values: colItems.map((x) => x.label),
      items: colItems,
    },
    matrix,
  };
}

export function buildEvidenceCodexPrompt(input: {
  strategy: string;
  revision: string;
  timeframe?: string;
  idea: string;
  notes: string;
  latestRun?: LibraryRun;
  latestCheck?: { kind: string; status: string; title?: string };
}): string {
  const revShort = input.revision ? input.revision.slice(0, 10) : 'chưa rõ';
  const tf = input.timeframe || 'theo chiến lược';
  const evidenceLines: string[] = [];

  if (input.latestRun) {
    const summary = formatLibraryRunSummary(input.latestRun);
    const timerange = String(input.latestRun.settings?.timerange ?? '—');
    const revState =
      input.latestRun.revision === input.revision
        ? 'khớp mã hiện tại'
        : 'mã đã sửa sau lần chạy này';
    evidenceLines.push(
      `- Gói backtest gần nhất: ${input.latestRun.id.slice(0, 10)} · khoảng ${timerange} · ${summary.contextText} (${revState})`,
    );
  } else {
    evidenceLines.push('- Gói backtest gần nhất: chưa có gói hoàn tất trên máy');
  }

  if (input.latestCheck) {
    const detail = input.latestCheck.title ? ` (${input.latestCheck.title})` : '';
    evidenceLines.push(
      `- Kiểm định gần nhất: ${input.latestCheck.kind} · ${input.latestCheck.status}${detail}`,
    );
  } else {
    evidenceLines.push('- Kiểm định gần nhất: chưa chạy lookahead / recursive');
  }

  return [
    `Trong dự án FreqPilot, hãy triển khai/chỉnh sửa chiến lược ${input.strategy} (mã ${revShort}, khung ${tf}) cho BTC/ETH Binance Futures isolated 1x, chỉ backtest và paper, giữ engine Freqtrade 2026.9.`,
    '',
    'Ý tưởng:',
    input.idea || '—',
    '',
    'Ghi chú:',
    input.notes || '—',
    '',
    'Bằng chứng hiện tại trên máy:',
    ...evidenceLines,
    '',
    'Đọc mã hiện có, nêu giả định, lưu phiên bản, kiểm tra cú pháp và chạy backtest với dữ liệu funding thực. Kiểm tra lookahead/recursive nếu thay đổi indicator hoặc thời điểm tín hiệu. Không tối ưu tự động, không đổi chiến lược paper đang chạy.',
  ].join('\n');
}

export type TradeAnalyticsResult = {
  underwater: { date: string; dd_pct: number }[];
  monthly: { year: number; month: number; profit_abs: number | null; trades: number }[];
  exitReasons: {
    reason: string;
    count: number;
    avg_profit: number | null;
    total_profit: number | null;
    wins: number;
    losses: number;
    winrate: number | null;
  }[];
  hourly: {
    hours: { hour: number; avg_profit: number | null; winrate: number | null; trades: number }[];
  };
  weekday: {
    days: {
      day: string;
      day_index: number;
      trades: number;
      avg_profit: number | null;
      total_profit: number | null;
      winrate: number | null;
    }[];
  };
};

const WEEKDAY_CODES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function buildTradeAnalytics(
  trades: Record<string, unknown>[] | undefined,
  startingBalance = 1000,
  windowRange?: { start?: string; end?: string },
): TradeAnalyticsResult {
  const list = trades ?? [];
  const allHaveFiniteAbsAndClose =
    list.length > 0 &&
    list.every(
      (t) =>
        typeof t.profit_abs === 'number' &&
        Number.isFinite(t.profit_abs) &&
        Number.isFinite(Date.parse(String(t.close_date ?? t.open_date ?? ''))),
    );

  const sorted = [...list].sort(
    (a, b) =>
      (Date.parse(String(a.close_date ?? a.open_date ?? '')) || 0) -
      (Date.parse(String(b.close_date ?? b.open_date ?? '')) || 0),
  );

  const hasValidStartingBalance =
    typeof startingBalance === 'number' && Number.isFinite(startingBalance) && startingBalance > 0;
  let balance = hasValidStartingBalance ? startingBalance : 1000;
  let peak = balance;
  const underwater: { date: string; dd_pct: number }[] = [];
  const monthlyByKey: Record<
    string,
    { year: number; month: number; profit_abs: number | null; trades: number }
  > = {};

  if (allHaveFiniteAbsAndClose && windowRange?.start && windowRange?.end) {
    const startMs = Date.parse(windowRange.start);
    const endMs = Date.parse(windowRange.end);
    if (Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs) {
      const startDate = new Date(startMs);
      const endDate = new Date(endMs);
      let y = startDate.getUTCFullYear();
      let m = startDate.getUTCMonth() + 1;
      const endY = endDate.getUTCFullYear();
      const endM = endDate.getUTCMonth() + 1;
      while (y < endY || (y === endY && m <= endM)) {
        monthlyByKey[`${y}-${m}`] = { year: y, month: m, profit_abs: 0, trades: 0 };
        m += 1;
        if (m > 12) {
          m = 1;
          y += 1;
        }
      }
    }
  }

  const reasonByKey: Record<
    string,
    {
      count: number;
      ratioPctSum: number;
      missingRatio: number;
      total_profit: number;
      missingAbs: number;
      wins: number;
      losses: number;
    }
  > = {};
  const hourBuckets = Array.from({ length: 24 }, (_, hour) => ({
    hour,
    ratioSum: 0,
    missingRatio: 0,
    missingAbs: 0,
    wins: 0,
    trades: 0,
  }));
  const dayBuckets = Array.from({ length: 7 }, (_, day_index) => ({
    day: WEEKDAY_CODES[day_index] ?? String(day_index),
    day_index,
    trades: 0,
    ratioPctSum: 0,
    missingRatio: 0,
    total_profit: 0,
    missingAbs: 0,
    wins: 0,
  }));

  for (const t of sorted) {
    const rawAbs = t.profit_abs;
    const hasAbs = typeof rawAbs === 'number' && Number.isFinite(rawAbs);
    const rawRatio = t.profit_ratio;
    const hasRatio = typeof rawRatio === 'number' && Number.isFinite(rawRatio);
    const closeStr = String(t.close_date ?? t.open_date ?? '');
    const closeMs = Date.parse(closeStr);

    if (allHaveFiniteAbsAndClose && hasValidStartingBalance && hasAbs && Number.isFinite(closeMs)) {
      balance += rawAbs;
      if (balance > peak) peak = balance;
      const ddPct = peak > 0 ? ((peak - balance) / peak) * 100 : 0;
      underwater.push({
        date: closeStr.slice(0, 16).replace('T', ' '),
        dd_pct: ddPct,
      });

      const closeDate = new Date(closeMs);
      const year = closeDate.getUTCFullYear();
      const month = closeDate.getUTCMonth() + 1;
      const mKey = `${year}-${month}`;
      const prevMonth = monthlyByKey[mKey] ?? { year, month, profit_abs: 0, trades: 0 };
      prevMonth.profit_abs = (prevMonth.profit_abs ?? 0) + rawAbs;
      prevMonth.trades += 1;
      monthlyByKey[mKey] = prevMonth;
    }

    const openMs = Date.parse(String(t.open_date ?? closeStr));
    if (Number.isFinite(openMs)) {
      const openDate = new Date(openMs);
      const hBucket = hourBuckets[openDate.getUTCHours()]!;
      hBucket.trades += 1;
      if (hasRatio) hBucket.ratioSum += rawRatio;
      else hBucket.missingRatio += 1;
      if (hasAbs) {
        if (rawAbs > 0) hBucket.wins += 1;
      } else {
        hBucket.missingAbs += 1;
      }

      const dayIdx = (openDate.getUTCDay() + 6) % 7;
      const dBucket = dayBuckets[dayIdx]!;
      dBucket.trades += 1;
      if (hasRatio) dBucket.ratioPctSum += rawRatio * 100;
      else dBucket.missingRatio += 1;
      if (hasAbs) {
        dBucket.total_profit += rawAbs;
        if (rawAbs > 0) dBucket.wins += 1;
      } else {
        dBucket.missingAbs += 1;
      }
    }

    const reason = String(t.exit_reason || t.sell_reason || 'unknown');
    const prevReason = reasonByKey[reason] ?? {
      count: 0,
      ratioPctSum: 0,
      missingRatio: 0,
      total_profit: 0,
      missingAbs: 0,
      wins: 0,
      losses: 0,
    };
    prevReason.count += 1;
    if (hasRatio) prevReason.ratioPctSum += rawRatio * 100;
    else prevReason.missingRatio += 1;
    if (hasAbs) {
      prevReason.total_profit += rawAbs;
      if (rawAbs > 0) prevReason.wins += 1;
      else prevReason.losses += 1;
    } else {
      prevReason.missingAbs += 1;
    }
    reasonByKey[reason] = prevReason;
  }

  return {
    underwater,
    monthly: Object.values(monthlyByKey).sort((a, b) => a.year - b.year || a.month - b.month),
    exitReasons: Object.entries(reasonByKey)
      .map(([reason, r]) => ({
        reason,
        count: r.count,
        avg_profit: r.count > 0 && r.missingRatio === 0 ? r.ratioPctSum / r.count : null,
        total_profit: r.count > 0 && r.missingAbs === 0 ? r.total_profit : null,
        wins: r.wins,
        losses: r.losses,
        winrate: r.count > 0 && r.missingAbs === 0 ? r.wins / r.count : null,
      }))
      .sort((a, b) => b.count - a.count),
    hourly: {
      hours: hourBuckets.map((h) => ({
        hour: h.hour,
        avg_profit: h.trades > 0 && h.missingRatio === 0 ? h.ratioSum / h.trades : null,
        winrate: h.trades > 0 && h.missingAbs === 0 ? h.wins / h.trades : null,
        trades: h.trades,
      })),
    },
    weekday: {
      days: dayBuckets.map((d) => ({
        day: d.day,
        day_index: d.day_index,
        trades: d.trades,
        avg_profit: d.trades > 0 && d.missingRatio === 0 ? d.ratioPctSum / d.trades : null,
        total_profit: d.trades > 0 && d.missingAbs === 0 ? d.total_profit : null,
        winrate: d.trades > 0 && d.missingAbs === 0 ? d.wins / d.trades : null,
      })),
    },
  };
}

export function buildResearchDossierMarkdown(input: {
  strategy: string;
  revision: string;
  idea?: string;
  notes?: string;
  tags?: string[];
  run: LibraryRun & {
    artifact_sha256?: string;
    input_files?: number;
    input_bytes?: number;
    summary?: {
      total_trades?: number;
      profit_total_abs?: number;
      profit_total?: number;
      max_drawdown_account?: number;
      profit_factor?: number;
      backtest_start?: string;
      backtest_end?: string;
      timeframe?: string;
    };
  };
  checks?: { kind: string; status: string }[];
  exitReasons?: {
    reason: string;
    count: number;
    avg_profit: number | null;
    total_profit: number | null;
    winrate: number | null;
  }[];
}): string {
  const s = input.run.summary;
  const trades = finiteNumber(s?.total_trades);
  const profitAbs = finiteNumber(s?.profit_total_abs);
  const profitPct = finiteNumber(s?.profit_total);
  const ddPct = finiteNumber(s?.max_drawdown_account);
  const pf = finiteNumber(s?.profit_factor);
  const presetText = input.run.preset
    ? `${input.run.preset.label} (SHA256: ${input.run.preset.native_sha256.slice(0, 12)})`
    : 'Tham số gốc trong mã';
  const checkLines = input.checks?.length
    ? input.checks.map((c) => `- **${c.kind}**: \`${c.status}\``)
    : ['- Chưa có báo cáo kiểm định lookahead / recursive.'];
  const exitRows = (input.exitReasons ?? []).map((r) => {
    const wr = r.winrate != null && Number.isFinite(r.winrate) ? `${(r.winrate * 100).toFixed(1)}%` : '—';
    const avg =
      r.avg_profit != null && Number.isFinite(r.avg_profit)
        ? `${r.avg_profit >= 0 ? '+' : ''}${r.avg_profit.toFixed(2)}%`
        : '—';
    const tot =
      r.total_profit != null && Number.isFinite(r.total_profit)
        ? `${r.total_profit >= 0 ? '+' : ''}${r.total_profit.toFixed(2)} USDT`
        : '—';
    return `| \`${r.reason}\` | ${r.count} | ${wr} | ${avg} | ${tot} |`;
  });

  return [
    `# Hồ sơ nghiên cứu (Dossier): ${input.strategy}`,
    '',
    '## 1. Định danh & Nguồn gốc (Provenance)',
    `- **Chiến lược**: \`${input.strategy}\``,
    `- **Mã nguồn (Revision SHA256)**: \`${input.revision || input.run.revision}\``,
    `- **Bộ tham số (Preset)**: ${presetText}`,
    `- **ID gói đóng băng**: \`${input.run.id}\``,
    `- **Dấu vân tay gói (Artifact SHA256)**: \`${input.run.artifact_sha256 ?? '—'}\``,
    `- **Engine**: Freqtrade 2026.9 chính thức (\`dry_run=true\`, Isolated 1x)`,
    '',
    '## 2. Ý tưởng & Giả định nghiên cứu',
    `- **Nhãn**: ${input.tags?.length ? input.tags.join(', ') : '—'}`,
    `- **Ý tưởng**: ${input.idea?.trim() || '—'}`,
    `- **Ghi chú & Giả định**: ${input.notes?.trim() || '—'}`,
    '',
    '## 3. Giao thức thử nghiệm (Frozen Protocol)',
    `- **Khoảng chạy (Timerange)**: \`${String(input.run.settings?.timerange ?? '—')}\``,
    `- **Khung tín hiệu / chi tiết**: \`${String(input.run.settings?.timeframe ?? s?.timeframe ?? '—')}\` / \`${String(input.run.settings?.timeframe_detail ?? '1m')}\``,
    `- **Vốn mô phỏng / Stake / Tối đa lệnh**: \`${String(input.run.settings?.dry_run_wallet ?? '—')} USDT\` / \`${String(input.run.settings?.stake_amount ?? '—')} USDT\` / \`${String(input.run.settings?.max_open_trades ?? '—')}\``,
    '',
    '## 4. Kết quả thực nghiệm trên mẫu đóng băng',
    '| Chỉ số | Giá trị |',
    '| :--- | :--- |',
    `| Số lệnh đã đóng | ${trades !== null ? `${trades} lệnh` : '—'} |`,
    `| Lãi / lỗ ròng (USDT) | ${profitAbs !== null ? `${profitAbs >= 0 ? '+' : ''}${profitAbs.toFixed(2)} USDT` : '—'} |`,
    `| Tỷ suất lợi nhuận (%) | ${profitPct !== null ? `${(profitPct * 100).toFixed(2)}%` : '—'} |`,
    `| Max Drawdown tài khoản | ${ddPct !== null ? `${(ddPct * 100).toFixed(2)}%` : '—'} |`,
    `| Profit Factor | ${pf !== null ? pf.toFixed(2) : '—'} |`,
    ...(exitRows.length
      ? [
          '',
          '### Phân bố theo lý do thoát lệnh (`exit_reason`)',
          '| Lý do thoát | Số lệnh | Winrate | TB lệnh (%) | Tổng lãi/lỗ |',
          '| :--- | ---: | ---: | ---: | ---: |',
          ...exitRows,
        ]
      : []),
    '',
    '## 5. Kiểm định kỹ thuật (Lookahead / Recursive)',
    ...checkLines,
    '',
    '## 6. Hướng dẫn kiểm chứng & Giới hạn bằng chứng',
    `1. Tải gói \`freqpilot-${input.run.id}.zip\` và mở FreqPilot \`/studio\` → **Nhập gói hồ sơ (.zip)**.`,
    `2. Đối chiếu dấu vân tay SHA256 kỳ vọng: \`${input.run.artifact_sha256 ?? '—'}\`.`,
    '3. Mở gói vừa nhập trong bước `05 · Kết quả` và nhấn **Chạy lại từ gói đã lưu (Archive Replay)** để kiểm tra đối chiếu từng lệnh (`matched` / `different` / `unavailable`).',
    '',
    '> **Giới hạn bằng chứng**: Gói lưu đóng băng mã Python local, bộ tham số và tệp nến/mark/funding local, nhưng không đóng băng metadata thị trường trực tuyến của Binance ở các gói cũ; kết quả này là bằng chứng thực nghiệm trên mẫu lịch sử, không phải cam kết lợi nhuận hay khả năng khớp lệnh tương lai.',
  ].join('\n');
}
