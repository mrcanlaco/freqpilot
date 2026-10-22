export type ResearchCheck = {
  id: string;
  kind: string;
  status: string;
  revision: string;
  strategy?: string;
  created_at: string;
  error?: string | null;
  settings?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  source_hashes?: Record<string, string>;
  preset?: { id: string; label: string; native_sha256: string } | null;
  progress_tasks?: Record<string, unknown>;
};
export type CheckContext = {
  strategy: string;
  revision: string;
  parameterRevision?: string;
  timeframe?: string;
  timerange?: string;
};
export type CheckAssessment = {
  tone: 'running' | 'incomplete' | 'attention' | 'bias' | 'limited';
  title: string;
  detail: string;
  missing: number;
  changed: number;
  signals?: number;
};
export function recordObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}
export function assessCheck(check: ResearchCheck): CheckAssessment {
  const base = { missing: 0, changed: 0 };
  if (['pending', 'running'].includes(check.status))
    return {
      ...base,
      tone: 'running',
      title: 'Đang thực hiện',
      detail: 'Chưa có kết luận kiểm định.',
    };
  if (check.status !== 'success' || !check.result)
    return {
      ...base,
      tone: 'incomplete',
      title: 'Chưa có kết luận',
      detail: check.error || 'Công cụ chưa trả về kết quả hoàn chỉnh.',
    };
  const result = check.result;
  if (check.kind === 'lookahead') {
    const signals =
      finite(result.total_signals) &&
      Number.isInteger(result.total_signals) &&
      result.total_signals >= 0
        ? result.total_signals
        : undefined;
    const flags = [result.biased_entry_signals, result.biased_exit_signals];
    const biased =
      result.has_bias === true ||
      flags.some((v) => finite(v) && v > 0) ||
      (Array.isArray(result.biased_indicators) && result.biased_indicators.length > 0);
    if (biased)
      return {
        ...base,
        signals,
        tone: 'bias',
        title: 'Có dấu hiệu lookahead',
        detail:
          'Engine báo tín hiệu hoặc indicator dùng thông tin không phù hợp thời điểm. Cần xem và sửa trước khi đánh giá hiệu suất.',
      };
    const minimum = finite(check.settings?.minimum_trade_amount)
      ? check.settings.minimum_trade_amount
      : 1;
    if (!signals || signals < minimum || result.has_bias !== false)
      return {
        ...base,
        signals,
        tone: 'incomplete',
        title: 'Chưa đủ dữ liệu để kết luận',
        detail: 'Thiếu kết luận native hoặc số tín hiệu chưa đạt mức tối thiểu của lần kiểm tra.',
      };
    const target = finite(check.settings?.targeted_trade_amount)
      ? check.settings.targeted_trade_amount
      : undefined;
    return {
      ...base,
      signals,
      tone: 'limited',
      title: `Chưa thấy bias trong ${signals} tín hiệu`,
      detail:
        (target && signals < target
          ? `Chỉ xét được ${signals}/${target} tín hiệu mong muốn. `
          : '') +
        'Đây là kết quả trên mẫu đã xét, không chứng minh không có bias ở mọi thời điểm hoặc có lợi nhuận.',
    };
  }
  if (check.kind === 'recursive') {
    const matrix = recordObject(result.results);
    if (!matrix)
      return {
        ...base,
        tone: 'incomplete',
        title: 'Thiếu bảng so sánh indicator',
        detail: 'Job hoàn tất nhưng chưa có kết quả recursive có thể đọc.',
      };
    let missing = 0,
      changed = 0,
      values = 0;
    for (const row of Object.values(matrix)) {
      const cells = recordObject(row);
      if (!cells) {
        missing++;
        continue;
      }
      for (const value of Object.values(cells)) {
        values++;
        if (!finite(value)) missing++;
        else if (value !== 0) changed++;
      }
    }
    if (missing)
      return {
        missing,
        changed,
        tone: 'attention',
        title: `Có ${missing} giá trị không tính được`,
        detail:
          'Ô null/NaN có thể do thiếu giá trị, mẫu warmup hoặc phép chia không xác định. Cần xem indicator và số nến tương ứng; job hoàn tất chưa phải kiểm định đạt.',
      };
    if (changed)
      return {
        missing,
        changed,
        tone: 'attention',
        title: `Có biến thiên ở ${changed} điểm so sánh`,
        detail:
          'Giá trị indicator thay đổi khi đổi số nến khởi động. Đọc mức biến thiên và tác động đến tín hiệu; giao diện không tự đặt ngưỡng đạt.',
      };
    return {
      ...base,
      tone: 'limited',
      title: values
        ? 'Không thấy biến thiên ở các ô được báo cáo'
        : 'Engine không báo cáo biến thiên',
      detail:
        'Kết quả giới hạn trong các indicator, cặp đầu tiên và đoạn dữ liệu đã xét. Ô không có trong báo cáo không được tự điền bằng 0.',
    };
  }
  return {
    ...base,
    tone: 'incomplete',
    title: 'Loại kiểm định chưa được diễn giải',
    detail: 'Xem kết quả native bên dưới.',
  };
}
export function checkContext(
  check: ResearchCheck,
  context: CheckContext,
): { state: 'same' | 'different' | 'unknown'; notes: string[] } {
  const notes: string[] = [];
  let unknown = false,
    differs = false;
  if (check.revision !== context.revision) {
    differs = true;
    notes.push('Mã chính khác phiên bản đang đối chiếu.');
  }
  if (check.strategy && check.strategy !== context.strategy) {
    differs = true;
    notes.push('Chiến lược khác mục đang đối chiếu.');
  }
  const parameter =
    check.preset?.native_sha256 ??
    (check.source_hashes
      ? (check.source_hashes['strategies/' + context.strategy + '.json'] ?? 'none')
      : undefined);
  if (!parameter || !context.parameterRevision) {
    unknown = true;
    notes.push('Thiếu dấu vân tay tham số để đối chiếu.');
  } else if (parameter !== context.parameterRevision) {
    differs = true;
    notes.push('Tệp/bộ tham số khác cấu hình đang đối chiếu.');
  }
  for (const [key, label] of [
    ['timeframe', 'Khung tín hiệu'],
    ['timerange', 'Khoảng ngày'],
  ] as const) {
    if (!check.settings?.[key] || !context[key]) {
      unknown = true;
      notes.push('Chưa đủ thông tin ' + label.toLowerCase() + '.');
    } else if (check.settings[key] !== context[key]) {
      differs = true;
      notes.push(label + ' khác cấu hình đang đối chiếu.');
    }
  }
  return { state: differs ? 'different' : unknown ? 'unknown' : 'same', notes };
}
