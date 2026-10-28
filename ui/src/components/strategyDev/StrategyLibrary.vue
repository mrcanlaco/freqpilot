<script setup lang="ts">
import { computed, ref } from 'vue';
import {
  filterAndSortStrategies,
  latestLibraryRuns,
  libraryUpdated,
  type LibraryRun,
  type LibraryStrategy,
  type StrategySortKey,
} from '@/utils/strategyLibrary';

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
  selectedTags = ref<string[]>([]),
  direction = ref<'all' | 'short' | 'long_only' | 'protected'>('all'),
  status = ref<'all' | 'archived' | 'matched' | 'changed' | 'unarchived' | 'invalid'>('all'),
  outcome = ref<'all' | 'profitable' | 'loss' | 'sample30' | 'small_sample'>('all'),
  sort = ref<StrategySortKey>('evidence'),
  view = ref('cards'),
  showAdvancedFilters = ref(false),
  chosen = ref<string[]>([]);
const latest = computed(() => latestLibraryRuns(props.runs));
const tags = computed(() =>
  [...new Set(props.items.flatMap((x) => x.research?.tags ?? []))].sort((a, b) =>
    a.localeCompare(b, 'vi'),
  ),
);
const tagCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const item of props.items) {
    for (const t of item.research?.tags ?? []) {
      counts[t] = (counts[t] ?? 0) + 1;
    }
  }
  return Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'vi'));
});
const frames = computed(() =>
  [...new Set(props.items.map((x) => x.timeframe).filter((x): x is string => !!x))].sort(),
);
const visible = computed(() =>
  filterAndSortStrategies(props.items, latest.value, {
    query: query.value,
    favorites: favorites.value,
    timeframe: timeframe.value,
    tag: tag.value,
    tags: selectedTags.value,
    direction: direction.value,
    status: status.value,
    outcome: outcome.value,
    sort: sort.value,
  }),
);
const archivedCount = computed(() => props.items.filter((x) => latest.value.has(x.name)).length);
const matchedCount = computed(
  () =>
    props.items.filter(
      (x) => latest.value.has(x.name) && latest.value.get(x.name)?.revision === x.revision,
    ).length,
);
const profitableCount = computed(
  () =>
    props.items.filter((x) => {
      const p = latest.value.get(x.name)?.summary?.profit_total_abs;
      return typeof p === 'number' && Number.isFinite(p) && p > 0;
    }).length,
);
const shortCount = computed(() => props.items.filter((x) => x.can_short === true).length);
const sample30Count = computed(
  () =>
    props.items.filter((x) => {
      const n = latest.value.get(x.name)?.summary?.total_trades;
      return typeof n === 'number' && Number.isFinite(n) && n >= 30;
    }).length,
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
    selectedTags.value.length > 0 ||
    direction.value !== 'all' ||
    status.value !== 'all' ||
    outcome.value !== 'all',
);
function selectVisibleArchived() {
  chosen.value = [...new Set([...chosen.value, ...visibleArchivedNames.value])];
}
function toggleTagChip(name: string) {
  if (tag.value === name) tag.value = '';
  if (selectedTags.value.includes(name)) {
    selectedTags.value = selectedTags.value.filter((x) => x !== name);
  } else {
    selectedTags.value = [...selectedTags.value, name];
  }
}
function reset() {
  query.value = '';
  favorites.value = false;
  timeframe.value = '';
  tag.value = '';
  selectedTags.value = [];
  direction.value = 'all';
  status.value = 'all';
  outcome.value = 'all';
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
const maxAbsProfit = computed(() => {
  let max = 10;
  for (const run of latest.value.values()) {
    const p = run.summary?.profit_total_abs;
    if (typeof p === 'number' && Number.isFinite(p)) {
      max = Math.max(max, Math.abs(p));
    }
  }
  return max;
});
function pnlBarPercent(value: number | undefined) {
  if (value == null || !Number.isFinite(value) || value === 0) return 0;
  return Math.min(100, Math.max(6, Math.round((Math.abs(value) / maxAbsProfit.value) * 100)));
}
function tradeBarPercent(trades: number | undefined) {
  if (trades == null || !Number.isFinite(trades) || trades <= 0) return 0;
  return Math.min(100, Math.round((trades / 30) * 100));
}
</script>

<template>
  <section class="strategy-library" aria-label="Thư viện chiến lược">
    <div class="library-title">
      <div>
        <h2>Thư viện chiến lược</h2>
      </div>
      <div class="actions">
        <button :disabled="busy" @click="emit('refresh')">Tải lại</button
        ><button class="primary" :disabled="busy" @click="emit('create')">+ Tạo chiến lược</button>
      </div>
    </div>
    <div class="visual-pipeline-strip" role="region" aria-label="Phễu kiểm định trực quan">
      <button type="button" class="vp-card" :class="{ active: !hasActiveFilters }" @click="reset">
        <div class="vp-top"><span>01 · Tổng Chiến Lược</span><b>{{ items.length }}</b></div>
        <div class="vp-bar"><div class="vp-fill accent" style="width: 100%" /></div>
        <small>{{ shortCount }} hỗ trợ Short · {{ items.length - shortCount }} Long-only</small>
      </button>
      <button type="button" class="vp-card" :class="{ active: status === 'archived' }" @click="status = status === 'archived' ? 'all' : 'archived'">
        <div class="vp-top"><span>02 · Đã Có Gói Backtest</span><b>{{ archivedCount }} / {{ items.length }}</b></div>
        <div class="vp-bar"><div class="vp-fill info" :style="{ width: (items.length ? Math.round((archivedCount / items.length) * 100) : 0) + '%' }" /></div>
        <small>{{ matchedCount }} chiến lược khớp mã hiện tại</small>
      </button>
      <button type="button" class="vp-card" :class="{ active: outcome === 'profitable' }" @click="outcome = outcome === 'profitable' ? 'all' : 'profitable'">
        <div class="vp-top"><span>03 · Có Lãi Ròng (&gt; 0 USDT)</span><b class="pos-text">{{ profitableCount }} / {{ archivedCount }}</b></div>
        <div class="vp-bar"><div class="vp-fill pos" :style="{ width: (archivedCount ? Math.round((profitableCount / archivedCount) * 100) : 0) + '%' }" /></div>
        <small>Lọc ngay các chiến lược sinh lời</small>
      </button>
      <button type="button" class="vp-card" :class="{ active: outcome === 'sample30' }" @click="outcome = outcome === 'sample30' ? 'all' : 'sample30'">
        <div class="vp-top"><span>04 · Đủ Mẫu (≥ 30 Lệnh)</span><b class="pos-text">{{ sample30Count }} / {{ archivedCount }}</b></div>
        <div class="vp-bar"><div class="vp-fill warn" :style="{ width: (archivedCount ? Math.round((sample30Count / archivedCount) * 100) : 0) + '%' }" /></div>
        <small>Đủ cỡ mẫu thống kê cơ bản</small>
      </button>
    </div>
    <div class="compact-control-bar">
      <input
        v-model="query"
        class="compact-search"
        type="search"
        aria-label="Tìm chiến lược"
        placeholder="Tìm tên chiến lược, ý tưởng, mã commit hoặc #nhãn…"
      />
      <select v-model="sort" class="compact-select" aria-label="Sắp xếp">
        <option value="evidence">Sắp xếp: Có gói backtest trước</option>
        <option value="profit_desc">Sắp xếp: Lãi/lỗ USDT (Cao → Thấp)</option>
        <option value="profit_asc">Sắp xếp: Lãi/lỗ USDT (Thấp → Cao)</option>
        <option value="return_desc">Sắp xếp: Tỷ suất % (Cao → Thấp)</option>
        <option value="drawdown_asc">Sắp xếp: Drawdown thấp nhất</option>
        <option value="trades_desc">Sắp xếp: Số lệnh (Nhiều → Ít)</option>
        <option value="run">Sắp xếp: Backtest gần nhất</option>
        <option value="updated">Sắp xếp: Cập nhật gần nhất</option>
        <option value="name">Sắp xếp: Tên A–Z</option>
        <option value="name_desc">Sắp xếp: Tên Z–A</option>
      </select>
      <button
        type="button"
        :class="{ active: showAdvancedFilters || hasActiveFilters }"
        @click="showAdvancedFilters = !showAdvancedFilters"
      >
        Bộ lọc &amp; Nhãn {{ hasActiveFilters ? '●' : '▾' }}
      </button>
      <div class="views" aria-label="Cách xem thư viện">
        <button :aria-pressed="view === 'cards'" @click="view = 'cards'">Thẻ</button
        ><button :aria-pressed="view === 'rows'" @click="view = 'rows'">Danh sách</button>
      </div>
      <button v-if="hasActiveFilters" class="ghost-btn" @click="reset">Xóa lọc</button>
      <span class="spacer" />
      <button
        v-if="visibleArchivedNames.length >= 2 && selection.length < visibleArchivedNames.length"
        :disabled="busy"
        @click="selectVisibleArchived"
      >
        Chọn nhanh ({{ visibleArchivedNames.length }})
      </button>
      <button v-if="selection.length" @click="chosen = []">Bỏ chọn ({{ selection.length }})</button>
      <button
        v-if="selection.length >= 2"
        class="primary"
        :disabled="busy"
        @click="emit('compare', selection)"
      >
        So sánh ({{ selection.length }})
      </button>
    </div>
    <div v-if="showAdvancedFilters || hasActiveFilters" class="advanced-filter-drawer">
      <div class="filters">
        <label
          >Khung tín hiệu<select v-model="timeframe">
            <option value="">Tất cả khung</option>
            <option v-for="tf in frames" :key="tf">{{ tf }}</option>
          </select></label
        ><label
          >Chiều &amp; Chế độ<select v-model="direction">
            <option value="all">Tất cả chiều</option>
            <option value="short">Hỗ trợ Short</option>
            <option value="long_only">Chỉ Long (không short)</option>
            <option value="protected">Đang bảo vệ Paper</option>
          </select></label
        ><label
          >Hồ sơ<select v-model="status">
            <option value="all">Tất cả hồ sơ</option>
            <option value="archived">Có gói backtest</option>
            <option value="matched">Mã khớp lần chạy gần nhất</option>
            <option value="changed">Mã khác lần chạy gần nhất</option>
            <option value="unarchived">Chưa có gói backtest</option>
            <option value="invalid">Cần sửa mã</option>
          </select></label
        ><label
          >Kết quả &amp; Cỡ mẫu<select v-model="outcome">
            <option value="all">Mọi kết quả</option>
            <option value="profitable">Có lãi ròng (&gt; 0 USDT)</option>
            <option value="loss">Đang lỗ (&lt; 0 USDT)</option>
            <option value="sample30">Đủ mẫu cơ bản (≥ 30 lệnh)</option>
            <option value="small_sample">Mẫu nhỏ (&lt; 30 lệnh)</option>
          </select></label
        ><label
          >Nhãn<select v-model="tag">
            <option value="">Tất cả nhãn</option>
            <option v-for="t in tags" :key="t">{{ t }}</option>
          </select></label
        ><label class="check" style="align-self:end;padding-bottom:8px"
          ><input v-model="favorites" type="checkbox" /> Chỉ yêu thích ({{ items.filter((x) => x.research?.is_favorite).length }})</label
        >
      </div>
      <div v-if="tagCounts.length" class="tag-filter-bar" role="region" aria-label="Lọc nhanh theo nhãn">
        <span class="tag-bar-label">Nhãn nhanh:</span>
        <button
          v-for="t in tagCounts"
          :key="t.name"
          type="button"
          class="tag-chip"
          :class="{ active: selectedTags.includes(t.name) || tag === t.name }"
          @click="toggleTagChip(t.name)"
        >
          #{{ t.name }} <small>{{ t.count }}</small>
        </button>
        <button
          v-if="selectedTags.length || tag"
          type="button"
          class="tag-chip clear"
          @click="selectedTags = []; tag = ''"
        >
          Bỏ lọc nhãn
        </button>
      </div>
    </div>
    <div v-if="!visible.length" class="empty">
      <h3>Không có chiến lược phù hợp</h3>
      <p>Thử tên, nhãn hoặc bộ lọc khác.</p>
      <button @click="reset">Xóa bộ lọc</button>
    </div>
    <div v-if="view === 'rows' && visible.length" class="rows-sort-header" role="region" aria-label="Sắp xếp nhanh danh sách">
      <button type="button" :class="{ active: sort === 'name' || sort === 'name_desc' }" @click="sort = sort === 'name' ? 'name_desc' : 'name'">
        Chiến lược {{ sort === 'name' ? '↑' : sort === 'name_desc' ? '↓' : '' }}
      </button>
      <button type="button" :class="{ active: sort === 'profit_desc' || sort === 'profit_asc' }" @click="sort = sort === 'profit_desc' ? 'profit_asc' : 'profit_desc'">
        Lãi/lỗ USDT {{ sort === 'profit_desc' ? '↓' : sort === 'profit_asc' ? '↑' : '' }}
      </button>
      <button type="button" :class="{ active: sort === 'return_desc' }" @click="sort = 'return_desc'">
        Tỷ suất % {{ sort === 'return_desc' ? '↓' : '' }}
      </button>
      <button type="button" :class="{ active: sort === 'drawdown_asc' }" @click="sort = 'drawdown_asc'">
        Drawdown {{ sort === 'drawdown_asc' ? '↑' : '' }}
      </button>
      <button type="button" :class="{ active: sort === 'trades_desc' }" @click="sort = 'trades_desc'">
        Số lệnh {{ sort === 'trades_desc' ? '↓' : '' }}
      </button>
      <button type="button" :class="{ active: sort === 'run' }" @click="sort = 'run'">
        Lần chạy gần nhất {{ sort === 'run' ? '↓' : '' }}
      </button>
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
            <button
              type="button"
              class="badge-btn tf-badge"
              :class="{ active: timeframe === item.timeframe }"
              @click="timeframe = timeframe === (item.timeframe ?? '') ? '' : (item.timeframe ?? '')"
            >
              {{ item.timeframe ?? 'Chưa rõ khung' }}
            </button>
            <span>{{
              item.can_short == null
                ? 'Chưa rõ chiều'
                : item.can_short
                  ? 'Hỗ trợ short'
                  : 'Không khai báo short'
            }}</span>
            <span v-if="item.protected" class="protected-badge">Paper chính · bảo vệ mã</span>
            <span v-if="item.invalid" class="warning">Cần sửa mã</span>
            <button
              v-for="t in item.research?.tags"
              :key="t"
              type="button"
              class="badge-btn tag"
              :class="{ active: selectedTags.includes(t) || tag === t }"
              @click="toggleTagChip(t)"
            >
              #{{ t }}
            </button>
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
            <div class="visual-evidence-bars" aria-hidden="true">
              <div class="ve-row">
                <span>Biên độ P&amp;L</span>
                <div class="ve-track">
                  <div
                    class="ve-fill"
                    :class="pnlTone(latest.get(item.name)?.summary?.profit_total_abs)"
                    :style="{ width: pnlBarPercent(latest.get(item.name)?.summary?.profit_total_abs) + '%' }"
                  />
                </div>
              </div>
              <div class="ve-row">
                <span>Cỡ mẫu ({{ latest.get(item.name)?.summary?.total_trades ?? 0 }}/30)</span>
                <div class="ve-track">
                  <div
                    class="ve-fill"
                    :class="(latest.get(item.name)?.summary?.total_trades ?? 0) >= 30 ? 'pos' : 'sample-warn'"
                    :style="{ width: tradeBarPercent(latest.get(item.name)?.summary?.total_trades) + '%' }"
                  />
                </div>
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
.visual-pipeline-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0 6px;
}
.vp-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 13px 15px;
  border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--line);
  text-align: left;
}
.vp-card.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, var(--bg));
}
.vp-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  width: 100%;
  gap: 8px;
}
.vp-top span {
  font-size: 12px;
  color: var(--fg-2);
  font-weight: 600;
}
.vp-top b {
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--fg);
}
.vp-top b.pos-text {
  color: #79dfb3;
}
.vp-bar {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: var(--bg-2);
  overflow: hidden;
}
.vp-fill {
  height: 100%;
  border-radius: 999px;
}
.vp-fill.accent {
  background: #38bdf8;
}
.vp-fill.info {
  background: #60a5fa;
}
.vp-fill.pos {
  background: #34d399;
}
.vp-fill.warn {
  background: #f59e0b;
}
.visual-evidence-bars {
  display: grid;
  gap: 6px;
  margin: 6px 0 10px;
  padding: 8px 10px;
  border-radius: 7px;
  background: var(--bg);
  border: 1px solid var(--line);
}
.ve-row {
  display: grid;
  grid-template-columns: 112px 1fr;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--fg-3);
}
.ve-track {
  height: 6px;
  border-radius: 999px;
  background: var(--bg-2);
  overflow: hidden;
}
.ve-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--fg-3);
}
.ve-fill.pos {
  background: #34d399;
}
.ve-fill.neg {
  background: #f43f5e;
}
.ve-fill.sample-warn {
  background: #e7bb72;
}
.compact-control-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 10px 0 14px;
}
.compact-search {
  flex: 1 1 260px;
  max-width: 420px;
  margin: 0 !important;
}
.compact-select {
  width: auto !important;
  min-width: 220px;
  margin: 0 !important;
}
.advanced-filter-drawer {
  padding: 12px;
  margin-bottom: 14px;
  border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--line);
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
  grid-template-columns: 1.8fr repeat(6, minmax(120px, 1fr));
  gap: 10px;
  margin: 14px 0 10px;
}
.tag-filter-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0 0 12px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.tag-bar-label {
  font-size: 11.5px;
  color: var(--fg-3);
  font-weight: 600;
  margin-right: 4px;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  font-size: 11.5px;
  border-radius: 999px;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  color: var(--fg-2);
}
.tag-chip.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 16%, var(--bg-1));
  color: var(--accent);
}
.tag-chip.clear {
  border-style: dashed;
  color: var(--fg-3);
}
.rows-sort-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.rows-sort-header button {
  padding: 5px 10px;
  font-size: 11.5px;
}
.rows-sort-header button.active {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, var(--bg-2));
}
.badge-btn {
  font-size: 10.5px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  padding: 3px 7px;
  border-radius: 5px;
  line-height: 1.3;
}
.badge-btn.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 18%, var(--bg-2));
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
