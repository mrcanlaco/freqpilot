<script setup lang="ts">
import { computed, ref } from 'vue';
import { latestLibraryRuns, libraryMatches, libraryUpdated } from '@/utils/strategyLibrary';
import type { LibraryStrategy, LibraryRun } from '@/utils/strategyLibrary';

const props = defineProps<{ items: LibraryStrategy[]; runs: LibraryRun[]; busy: boolean }>();
const emit = defineEmits<{
  open: [name: string, tab: string];
  create: [];
  favorite: [name: string, value: boolean];
  compare: [names: string[]];
  refresh: [];
}>();
const query = ref(''),
  favorites = ref(false),
  timeframe = ref(''),
  tag = ref(''),
  status = ref('all'),
  sort = ref('evidence'),
  view = ref('cards'),
  chosen = ref<string[]>([]);
const latest = computed(() => latestLibraryRuns(props.runs));
const tags = computed(() =>
  [...new Set(props.items.flatMap((x) => x.research?.tags ?? []))].sort((a, b) =>
    a.localeCompare(b, 'vi'),
  ),
);
const frames = computed(() =>
  [...new Set(props.items.map((x) => x.timeframe).filter((x): x is string => !!x))].sort(),
);
const visible = computed(() =>
  props.items
    .filter(
      (x) =>
        libraryMatches(x, query.value) &&
        (!favorites.value || x.research?.is_favorite) &&
        (!timeframe.value || x.timeframe === timeframe.value) &&
        (!tag.value || x.research?.tags?.includes(tag.value)) &&
        (status.value === 'all' ||
          (status.value === 'archived'
            ? latest.value.has(x.name)
            : status.value === 'changed'
              ? !!latest.value.get(x.name) && latest.value.get(x.name)?.revision !== x.revision
              : status.value === 'invalid'
                ? x.invalid
                : !latest.value.has(x.name))),
    )
    .sort((a, b) => {
      if (sort.value === 'name') return a.name.localeCompare(b.name);
      if (sort.value === 'run')
        return (
          (Date.parse(latest.value.get(b.name)?.created_at ?? '') || 0) -
          (Date.parse(latest.value.get(a.name)?.created_at ?? '') || 0)
        );
      if (sort.value === 'evidence') {
        const hasA = latest.value.has(a.name) ? 1 : 0;
        const hasB = latest.value.has(b.name) ? 1 : 0;
        if (hasA !== hasB) return hasB - hasA;
      }
      return libraryUpdated(b) - libraryUpdated(a);
    }),
);
const archivedCount = computed(() => props.items.filter((x) => latest.value.has(x.name)).length);
const matchedCount = computed(
  () =>
    props.items.filter(
      (x) => latest.value.has(x.name) && latest.value.get(x.name)?.revision === x.revision,
    ).length,
);
const visibleArchivedNames = computed(() =>
  visible.value.filter((x) => latest.value.has(x.name)).map((x) => x.name),
);
const selection = computed(() =>
  chosen.value.filter((name) => props.items.some((x) => x.name === name) && latest.value.has(name)),
);
const hasActiveFilters = computed(
  () =>
    !!query.value ||
    favorites.value ||
    !!timeframe.value ||
    !!tag.value ||
    status.value !== 'all',
);
function selectVisibleArchived() {
  chosen.value = [...new Set([...chosen.value, ...visibleArchivedNames.value])];
}
function reset() {
  query.value = '';
  favorites.value = false;
  timeframe.value = '';
  tag.value = '';
  status.value = 'all';
}
function pnlTone(value: number | undefined) {
  if (value == null || !Number.isFinite(value) || value === 0) return '';
  return value > 0 ? 'pos' : 'neg';
}
function number(value: number | undefined, digits = 2) {
  return value == null || !Number.isFinite(value)
    ? '—'
    : value.toLocaleString('vi-VN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
}
function date(value: number | string | undefined) {
  return value ? new Date(value).toLocaleString('vi-VN') : '—';
}
</script>

<template>
  <section class="strategy-library" aria-label="Thư viện chiến lược">
    <div class="library-title">
      <div>
        <span class="eyebrow">STRATEGIES · FREQPILOT</span>
        <h2>Thư viện chiến lược</h2>
        <p>Chọn một ý tưởng, xem bằng chứng rồi tiếp tục nghiên cứu.</p>
      </div>
      <div class="actions">
        <button :disabled="busy" @click="emit('refresh')">Tải lại thư viện</button
        ><button class="primary" :disabled="busy" @click="emit('create')">+ Tạo chiến lược</button>
      </div>
    </div>
    <div class="totals" role="region" aria-label="Thống kê nhanh thư viện">
      <button
        type="button"
        class="total-pill"
        :class="{ active: !hasActiveFilters }"
        @click="reset"
      >
        <span>Tổng cộng</span><b>{{ items.length }}</b>
      </button>
      <span class="total-pill static">
        <span>Đang hiển thị</span><b>{{ visible.length }}</b>
      </span>
      <button
        type="button"
        class="total-pill"
        :class="{ active: favorites }"
        @click="favorites = !favorites"
      >
        <span>Yêu thích</span><b>{{ items.filter((x) => x.research?.is_favorite).length }}</b>
      </button>
      <button
        type="button"
        class="total-pill"
        :class="{ active: status === 'archived' }"
        @click="status = status === 'archived' ? 'all' : 'archived'"
      >
        <span>Có gói backtest</span><b>{{ archivedCount }}</b>
      </button>
      <button
        type="button"
        class="total-pill"
        :class="{ active: status === 'changed' }"
        @click="status = status === 'changed' ? 'all' : 'changed'"
      >
        <span>Mã khớp / đã đổi</span><b>{{ matchedCount }} / {{ archivedCount - matchedCount }}</b>
      </button>
    </div>
    <div class="filters">
      <label class="search"
        >Tìm chiến lược<input
          v-model="query"
          type="search"
          placeholder="Tên, mô tả hoặc nhãn…" /></label
      ><label
        >Khung tín hiệu<select v-model="timeframe">
          <option value="">Tất cả khung</option>
          <option v-for="tf in frames" :key="tf">{{ tf }}</option>
        </select></label
      ><label
        >Nhãn<select v-model="tag">
          <option value="">Tất cả nhãn</option>
          <option v-for="t in tags" :key="t">{{ t }}</option>
        </select></label
      ><label
        >Hồ sơ<select v-model="status">
          <option value="all">Tất cả</option>
          <option value="archived">Có gói backtest</option>
          <option value="changed">Mã khác lần chạy gần nhất</option>
          <option value="unarchived">Chưa có gói backtest</option>
          <option value="invalid">Cần sửa mã</option>
        </select></label
      ><label
        >Sắp xếp<select v-model="sort">
          <option value="evidence">Có gói backtest trước</option>
          <option value="updated">Cập nhật gần nhất</option>
          <option value="name">Tên A–Z</option>
          <option value="run">Backtest gần nhất</option>
        </select></label
      >
    </div>
    <div class="toolbar">
      <label class="check"><input v-model="favorites" type="checkbox" /> Chỉ yêu thích</label>
      <div class="views" aria-label="Cách xem thư viện">
        <button :aria-pressed="view === 'cards'" @click="view = 'cards'">Thẻ</button
        ><button :aria-pressed="view === 'rows'" @click="view = 'rows'">Danh sách</button>
      </div>
      <button v-if="hasActiveFilters" class="ghost-btn" @click="reset">Xóa bộ lọc</button>
      <span class="spacer" />
      <button
        v-if="visibleArchivedNames.length >= 2 && selection.length < visibleArchivedNames.length"
        :disabled="busy"
        @click="selectVisibleArchived"
      >
        Chọn nhanh có gói ({{ visibleArchivedNames.length }})
      </button>
      <span v-if="selection.length" class="selection-badge"
        >Đã chọn {{ selection.length }} · kể cả mục đang lọc</span
      ><button v-if="selection.length" @click="chosen = []">Bỏ chọn</button
      ><button
        class="primary"
        :disabled="busy || selection.length < 2"
        @click="emit('compare', selection)"
      >
        So sánh đã chọn ({{ selection.length }})
      </button>
    </div>
    <p class="evidence-note">
      Chỉ số lấy từ gói backtest hoàn tất gần nhất đã tải, không chọn kết quả tốt nhất. Khung, ngày
      và mã có thể khác nhau; đây không phải xếp hạng chất lượng. Báo cáo cũ chưa có gói vẫn xem
      được trong trang chiến lược.
    </p>
    <div v-if="!visible.length" class="empty">
      <h3>Không có chiến lược phù hợp</h3>
      <p>Thử tên, nhãn hoặc bộ lọc khác.</p>
      <button @click="reset">Xóa bộ lọc</button>
    </div>
    <div class="entries" :class="view">
      <article
        v-for="item in visible"
        :key="item.name"
        class="entry"
        :class="{
          'has-evidence': latest.has(item.name),
          'is-selected': selection.includes(item.name),
          'is-favorite': !!item.research?.is_favorite,
        }"
      >
        <div class="identity">
          <div class="entry-heading">
            <button class="name" :disabled="busy" @click="emit('open', item.name, 'idea')">
              {{ item.name }}</button
            ><button
              class="star"
              :class="{ starred: !!item.research?.is_favorite }"
              :aria-label="'Yêu thích ' + item.name"
              :aria-pressed="!!item.research?.is_favorite"
              :disabled="busy"
              @click="emit('favorite', item.name, !item.research?.is_favorite)"
            >
              {{ item.research?.is_favorite ? '★' : '☆' }}
            </button>
          </div>
          <p class="description">
            {{ item.research?.idea || 'Chưa có mô tả. Mở chiến lược để ghi lại ý tưởng.' }}
          </p>
          <div class="badges">
            <span class="tf-badge">{{ item.timeframe ?? 'Chưa rõ khung' }}</span
            ><span>{{
              item.can_short == null
                ? 'Chưa rõ chiều'
                : item.can_short
                  ? 'Hỗ trợ short'
                  : 'Không khai báo short'
            }}</span
            ><span v-if="item.protected" class="protected-badge">Paper chính · bảo vệ mã</span
            ><span v-if="item.invalid" class="warning">Cần sửa mã</span
            ><span v-for="t in item.research?.tags" :key="t" class="tag">{{ t }}</span>
          </div>
          <small>Cập nhật {{ date(libraryUpdated(item)) }}</small>
        </div>
        <div class="evidence">
          <small v-if="latest.get(item.name)?.preset" class="preset-pill"
            >Bộ tham số: {{ latest.get(item.name)?.preset?.label }}</small
          >
          <template v-if="latest.get(item.name)"
            ><div class="metrics">
              <div class="metric-cell">
                <small>Lãi/lỗ · USDT</small
                ><b :class="pnlTone(latest.get(item.name)?.summary?.profit_total_abs)">{{
                  number(latest.get(item.name)?.summary?.profit_total_abs)
                }}</b>
              </div>
              <div class="metric-cell">
                <small>Lợi nhuận</small
                ><b :class="pnlTone(latest.get(item.name)?.summary?.profit_total)"
                  >{{
                    number(
                      latest.get(item.name)?.summary?.profit_total == null
                        ? undefined
                        : latest.get(item.name)!.summary!.profit_total! * 100,
                    )
                  }}%</b
                >
              </div>
              <div class="metric-cell">
                <small>Drawdown</small
                ><b
                  >{{
                    number(
                      latest.get(item.name)?.summary?.max_drawdown_account == null
                        ? undefined
                        : latest.get(item.name)!.summary!.max_drawdown_account! * 100,
                    )
                  }}%</b
                >
              </div>
              <div class="metric-cell">
                <small>Số lệnh</small
                ><b>{{ number(latest.get(item.name)?.summary?.total_trades, 0) }}</b>
              </div>
            </div>
            <small class="run-meta"
              >Chạy {{ date(latest.get(item.name)?.created_at) }} ·
              {{ latest.get(item.name)?.settings.timeframe }} ·
              {{ latest.get(item.name)?.settings.timerange }}</small
            >
            <p
              class="status"
              :class="{ warning: latest.get(item.name)?.revision !== item.revision }"
            >
              {{
                latest.get(item.name)?.revision === item.revision
                  ? '✓ Mã khớp lần backtest này'
                  : '● Mã hiện tại khác bản đã backtest'
              }}
              · {{ latest.get(item.name)?.revision.slice(0, 10) }}
            </p>
            <p
              v-if="(latest.get(item.name)?.summary?.total_trades ?? 0) < 30"
              class="warning sample"
            >
              Mẫu dưới 30 lệnh, chưa đủ kết luận chất lượng.
            </p></template
          >
          <div v-else class="no-run">
            <b>Chưa có gói backtest</b>
            <p>Lưu mã và chạy từ workspace để có hồ sơ đầu vào/kết quả.</p>
          </div>
        </div>
        <div class="entry-actions">
          <label class="check" :class="{ disabled: !latest.has(item.name) }"
            ><input
              v-model="chosen"
              type="checkbox"
              :value="item.name"
              :disabled="!latest.has(item.name)"
              :aria-label="'Chọn so sánh ' + item.name"
            />
            So sánh</label
          ><button :disabled="busy" @click="emit('open', item.name, 'idea')">Ý tưởng</button
          ><button :disabled="busy" @click="emit('open', item.name, 'code')">Mở mã</button
          ><button
            class="action-highlight"
            :disabled="busy"
            @click="emit('open', item.name, latest.has(item.name) ? 'results' : 'run')"
          >
            {{ latest.has(item.name) ? 'Xem kết quả' : 'Backtest' }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.strategy-library,
.strategy-library p,
.strategy-library h2,
.strategy-library h3,
.strategy-library label,
.strategy-library small,
.strategy-library div {
  text-align: left;
}
.strategy-library {
  border: 1px solid var(--line);
  background: var(--bg-1);
  border-radius: 14px;
  padding: 24px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.22);
}
.library-title,
.actions,
.toolbar,
.totals,
.entry-heading,
.badges,
.entry-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.library-title {
  justify-content: space-between;
  margin-bottom: 14px;
}
.eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--accent);
}
h2 {
  font-size: 24px;
  font-weight: 650;
  margin: 4px 0 4px;
}
p {
  color: var(--fg-2);
  line-height: 1.55;
  margin: 0;
}
button {
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  font-weight: 500;
  padding: 8px 12px;
  border-radius: 7px;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s, color 0.15s;
}
button:hover:not(:disabled),
button[aria-pressed='true'] {
  border-color: var(--accent);
  color: var(--accent);
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
.primary {
  background: #1b6a5c;
  border-color: #268b77;
  color: #f2fff9;
}
.primary:hover:not(:disabled) {
  background: #217d6d;
  color: #fff;
}
.action-highlight {
  border-color: rgba(38, 139, 119, 0.55);
  background: rgba(27, 106, 92, 0.18);
  color: #8ce5c0;
}
.ghost-btn {
  background: transparent;
  color: var(--fg-2);
}
.totals {
  padding: 14px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  gap: 10px;
}
.total-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--fg-2);
  font-size: 12.5px;
}
.total-pill.static {
  cursor: default;
}
.total-pill.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, var(--bg));
  color: var(--fg);
}
.total-pill b {
  color: var(--fg);
  font-variant-numeric: tabular-nums;
  font-size: 13.5px;
}
.filters {
  display: grid;
  grid-template-columns: 2fr repeat(4, 1fr);
  gap: 12px;
  margin: 16px 0;
}
.filters label {
  font-size: 12px;
  color: var(--fg-2);
  font-weight: 500;
}
input:not([type='checkbox']),
select {
  display: block;
  width: 100%;
  font: inherit;
  font-size: 13px;
  background: var(--bg);
  color: var(--fg);
  border: 1px solid var(--line-2);
  border-radius: 7px;
  padding: 9px 11px;
  margin-top: 6px;
}
input:not([type='checkbox']):focus,
select:focus {
  outline: none;
  border-color: var(--accent);
}
.toolbar {
  font-size: 12.5px;
  padding: 10px 14px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 9px;
}
.selection-badge {
  color: var(--accent);
  font-weight: 500;
}
.check {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  cursor: pointer;
}
.check.disabled {
  opacity: 0.45;
  cursor: default;
}
.check input {
  accent-color: var(--accent);
}
.spacer {
  flex: 1;
}
.views {
  display: flex;
  gap: 4px;
}
.evidence-note {
  font-size: 12px;
  color: var(--fg-3);
  margin: 12px 0 16px;
}
.entries.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.entry {
  border: 1px solid var(--line);
  background: var(--bg);
  border-radius: 11px;
  padding: 18px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: border-color 0.15s, transform 0.15s;
}
.entry:hover {
  border-color: var(--line-2);
}
.entry.has-evidence {
  border-top: 2px solid rgba(38, 139, 119, 0.7);
}
.entry.is-selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.identity {
  min-width: 0;
}
.entry-heading {
  flex-wrap: nowrap;
  align-items: start;
  justify-content: space-between;
}
.name {
  font-size: 16px;
  font-weight: 650;
  border: 0;
  background: none;
  padding: 0;
  text-align: left;
  overflow-wrap: anywhere;
}
.star {
  font-size: 20px;
  line-height: 1;
  padding: 2px 5px;
  border: 0;
  background: none;
  color: var(--fg-3);
}
.star.starred {
  color: #f3c969;
}
.description {
  font-size: 12.5px;
  margin: 8px 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 38px;
  color: var(--fg-2);
}
.badges {
  gap: 6px;
  margin: 8px 0;
}
.badges span {
  font-size: 10.5px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  padding: 3px 7px;
  border-radius: 5px;
}
.badges .tf-badge {
  font-weight: 600;
  color: var(--fg);
}
.badges .protected-badge {
  background: rgba(27, 106, 92, 0.2);
  border-color: rgba(38, 139, 119, 0.5);
  color: #8ce5c0;
}
.badges .tag {
  color: var(--accent);
}
small {
  color: var(--fg-3);
  font-size: 11px;
  line-height: 1.5;
}
.preset-pill {
  display: inline-block;
  margin-bottom: 8px;
  padding: 3px 8px;
  border-radius: 5px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  color: var(--fg-2);
}
.evidence {
  margin-top: auto;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-1);
  border: 1px solid var(--line);
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 10px;
}
.metric-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metrics b {
  font-size: 14.5px;
  font-variant-numeric: tabular-nums;
}
.metrics b.pos {
  color: #79dfb3;
}
.metrics b.neg {
  color: #f29b9b;
}
.run-meta {
  display: block;
}
.status {
  font-size: 11px;
  color: #79dfb3;
  margin: 6px 0 0;
  font-weight: 500;
}
.warning {
  color: #e7bb72 !important;
}
.sample {
  font-size: 11px;
  margin: 5px 0 0;
}
.entry-actions {
  border-top: 1px solid var(--line);
  padding-top: 12px;
  margin-top: auto;
  gap: 6px;
}
.entry-actions .check {
  margin-right: auto;
}
.no-run {
  font-size: 12.5px;
  color: var(--fg-3);
  min-height: 76px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}
.entries.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rows .entry {
  display: grid;
  grid-template-columns: minmax(230px, 1.1fr) minmax(350px, 1.2fr) auto;
  align-items: center;
  gap: 20px;
}
.rows .description {
  min-height: 0;
  -webkit-line-clamp: 2;
}
.rows .entry-actions {
  border: 0;
  flex-direction: row;
  padding: 0;
}
.rows .entry-actions .check {
  margin-right: 8px;
}
.rows .evidence {
  margin: 0;
}
.empty {
  padding: 48px;
  text-align: center !important;
  color: var(--fg-3);
}
@media (max-width: 1300px) {
  .entries.cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .rows .entry {
    grid-template-columns: 1fr 1fr;
  }
  .rows .entry-actions {
    grid-column: 1/-1;
    flex-direction: row;
    justify-content: end;
  }
}
@media (max-width: 850px) {
  .filters {
    grid-template-columns: repeat(2, 1fr);
  }
  .filters .search {
    grid-column: 1/-1;
  }
  .entries.cards,
  .rows .entry {
    display: flex;
    flex-direction: column;
  }
  .rows .entry {
    align-items: stretch;
  }
  .strategy-library {
    padding: 16px;
  }
  .metrics b {
    font-size: 13.5px;
  }
}
</style>
