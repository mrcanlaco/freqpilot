<script setup lang="ts">
import { computed } from 'vue';
import {
  assessCheck,
  checkContext,
  recordObject,
  type ResearchCheck,
  type CheckContext,
} from '@/utils/researchChecks';
const props = defineProps<{ check: ResearchCheck; context: CheckContext }>();
const assessment = computed(() => assessCheck(props.check));
const match = computed(() => checkContext(props.check, props.context));
const states: Record<string, string> = {
  pending: 'Đang xử lý',
  running: 'Đang xử lý',
  success: 'Đã hoàn tất',
  failed: 'Không hoàn tất',
  interrupted: 'Bị gián đoạn',
};
const matrix = computed(() => recordObject(props.check.result?.results));
const candles = computed(() =>
  [
    ...new Set([
      ...(Array.isArray(props.check.result?.startup_candles)
        ? props.check.result.startup_candles.map(String)
        : []),
      ...Object.values(matrix.value ?? {}).flatMap((row) => Object.keys(recordObject(row) ?? {})),
    ]),
  ].sort((a, b) => Number(a) - Number(b)),
);
function cell(row: unknown, candle: string) {
  const values = recordObject(row);
  if (!values || !Object.hasOwn(values, candle)) return 'Không báo cáo';
  const n = values[candle];
  return typeof n === 'number' && Number.isFinite(n)
    ? (n * 100).toLocaleString('vi-VN', { maximumSignificantDigits: 7 }) + '%'
    : 'Không tính được';
}
</script>
<template>
  <article class="check-report">
    <header>
      <b>{{ check.kind === 'lookahead' ? 'Lookahead' : 'Warmup / Recursive' }}</b
      ><span>Thực thi: {{ states[check.status] ?? check.status }}</span
      ><small
        >{{ new Date(check.created_at).toLocaleString('vi-VN') }} · mã
        {{ check.revision.slice(0, 10) }}</small
      >
    </header>
    <div class="assessment" :class="assessment.tone">
      <h4>{{ assessment.title }}</h4>
      <p>{{ assessment.detail }}</p>
    </div>
    <p v-if="check.preset">
      Bộ tham số đã kiểm định: <b>{{ check.preset.label }}</b> ·
      {{ check.preset.native_sha256.slice(0, 10) }}.
    </p>
    <p class="context" :class="{ different: match.state !== 'same' }">
      {{
        match.state === 'same'
          ? 'Mã chính, tham số, khung và khoảng ngày khớp cấu hình đang đối chiếu.'
          : match.state === 'different'
            ? 'Kết quả thuộc cấu hình khác.'
            : 'Chưa đối chiếu đầy đủ ngữ cảnh.'
      }}<span v-for="note in match.notes" :key="note"> {{ note }}</span>
    </p>
    <p v-if="check.settings" class="settings">
      Cấu hình lúc chạy: {{ check.settings.timeframe ?? '—' }} · {{ check.settings.timerange ?? '—'
      }}<template v-if="check.result?.strategy_scc != null">
        · warmup khai báo {{ check.result.strategy_scc }} nến</template
      >.
    </p>
    <details v-if="check.kind === 'recursive' && matrix && Object.keys(matrix).length">
      <summary>Xem bảng biến thiên indicator</summary>
      <p>
        Tỷ lệ chênh lệch từ engine được đổi sang %. “Không báo cáo” và “Không tính được” được giữ
        riêng, không thay bằng 0.
      </p>
      <div class="scroll">
        <table>
          <thead>
            <tr>
              <th>Indicator</th>
              <th v-for="candle in candles" :key="candle">{{ candle }} nến</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, name) in matrix" :key="name">
              <th>{{ name }}</th>
              <td
                v-for="candle in candles"
                :key="candle"
                :class="{ missing: cell(row, candle) === 'Không tính được' }"
              >
                {{ cell(row, candle) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
    <details v-if="check.result">
      <summary>Kết quả gốc từ Freqtrade</summary>
      <pre>{{ JSON.stringify(check.result, null, 2) }}</pre>
    </details>
    <p v-if="check.error" class="error">{{ check.error }}</p>
  </article>
</template>
<style scoped>
.check-report,
.check-report * {
  text-align: left;
}
.check-report {
  border: 1px solid var(--line);
  background: var(--bg);
  border-radius: 10px;
  padding: 18px 20px;
  margin: 14px 0;
  color: var(--fg);
}
header {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
}
header span {
  font-size: 12px;
  color: var(--fg-3);
}
small,
.settings {
  font-size: 11px;
  color: var(--fg-3);
}
p {
  font-size: 13px;
  line-height: 1.65;
  text-align: left;
  margin: 10px 0;
}
h4 {
  font-size: 15px;
  margin: 0;
}
.assessment {
  margin: 16px 0;
  padding: 14px 16px;
  border-left: 3px solid #7b9ebe;
  background: #18232d;
}
.assessment p {
  margin: 7px 0 0;
}
.attention,
.incomplete {
  border-color: #d7ad66;
  background: #342b1d;
}
.bias {
  border-color: #e68989;
  background: #3b2429;
}
.running {
  border-color: #8d95a1;
  background: #24282e;
}
.context {
  font-size: 12px;
  color: var(--fg-3);
}
.different,
.missing {
  color: #e1b779;
}
.scroll {
  overflow: auto;
}
table {
  font-size: 12px;
  width: 100%;
  margin: 12px 0;
  border-collapse: collapse;
}
th,
td {
  padding: 10px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
details {
  margin-top: 16px;
}
summary {
  font-size: 13px;
  color: var(--accent);
  cursor: pointer;
}
pre {
  font-size: 12px;
  background: var(--bg);
  padding: 15px;
  max-height: 400px;
  overflow: auto;
}
.error {
  color: #ffb4b4;
}
</style>
