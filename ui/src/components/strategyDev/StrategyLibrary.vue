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
  sort = ref('updated'),
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
    .sort((a, b) =>
      sort.value === 'name'
        ? a.name.localeCompare(b.name)
        : sort.value === 'run'
          ? (Date.parse(latest.value.get(b.name)?.created_at ?? '') || 0) -
            (Date.parse(latest.value.get(a.name)?.created_at ?? '') || 0)
          : libraryUpdated(b) - libraryUpdated(a),
    ),
);
const selection = computed(() =>
  chosen.value.filter((name) => props.items.some((x) => x.name === name) && latest.value.has(name)),
);
function reset() {
  query.value = '';
  favorites.value = false;
  timeframe.value = '';
  tag.value = '';
  status.value = 'all';
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
    <div class="totals">
      <span
        >Tổng cộng <b>{{ items.length }}</b></span
      ><span
        >Đang hiển thị <b>{{ visible.length }}</b></span
      ><span
        >Yêu thích <b>{{ items.filter((x) => x.research?.is_favorite).length }}</b></span
      ><span
        >Có gói backtest <b>{{ items.filter((x) => latest.has(x.name)).length }}</b></span
      >
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
      <span class="spacer" /><span v-if="selection.length"
        >Đã chọn {{ selection.length }} · kể cả mục đang lọc</span
      ><button v-if="selection.length" @click="chosen = []">Bỏ chọn</button
      ><button :disabled="busy || selection.length < 2" @click="emit('compare', selection)">
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
      <article v-for="item in visible" :key="item.name" class="entry">
        <div class="identity">
          <div class="entry-heading">
            <button class="name" :disabled="busy" @click="emit('open', item.name, 'idea')">
              {{ item.name }}</button
            ><button
              class="star"
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
            <span>{{ item.timeframe ?? 'Chưa rõ khung' }}</span
            ><span>{{ item.can_short == null ? 'Chưa rõ chiều' : item.can_short ? 'Hỗ trợ short' : 'Không khai báo short' }}</span
            ><span v-if="item.protected">Paper chính · bảo vệ mã</span
            ><span v-if="item.invalid" class="warning">Cần sửa mã</span
            ><span v-for="t in item.research?.tags" :key="t" class="tag">{{ t }}</span>
          </div>
          <small>Cập nhật {{ date(libraryUpdated(item)) }}</small>
        </div>
        <div class="evidence"><small v-if="latest.get(item.name)?.preset">Bộ tham số: {{latest.get(item.name)?.preset?.label}}</small>
          <template v-if="latest.get(item.name)"
            ><div class="metrics">
              <div>
                <small>Lãi/lỗ · USDT</small
                ><b>{{ number(latest.get(item.name)?.summary?.profit_total_abs) }}</b>
              </div>
              <div>
                <small>Lợi nhuận</small
                ><b
                  >{{
                    number(
                      latest.get(item.name)?.summary?.profit_total == null
                        ? undefined
                        : latest.get(item.name)!.summary!.profit_total! * 100,
                    )
                  }}%</b
                >
              </div>
              <div>
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
              <div>
                <small>Số lệnh</small
                ><b>{{ number(latest.get(item.name)?.summary?.total_trades, 0) }}</b>
              </div>
            </div>
            <small
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
                  ? 'Mã khớp lần backtest này'
                  : 'Mã hiện tại khác bản đã backtest'
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
          <label class="check"
            ><input
              v-model="chosen"
              type="checkbox"
              :value="item.name"
              :disabled="!latest.has(item.name)"
              :aria-label="'Chọn so sánh ' + item.name"
            />
            So sánh</label
          ><button :disabled="busy" @click="emit('open', item.name, 'code')">Mở mã</button
          ><button
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
.strategy-library p,.strategy-library h2,.strategy-library label,.strategy-library small{text-align:left}
.strategy-library {
  border: 1px solid var(--line);
  background: var(--bg-1);
  border-radius: 14px;
  padding: 24px;
}
.library-title,
.actions,
.toolbar,
.totals,
.entry-heading,
.badges,
.entry-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.library-title {
  justify-content: space-between;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--accent);
}
h2 {
  font-size: 26px;
  margin: 8px 0;
}
p {
  color: var(--fg-2);
  line-height: 1.6;
}
button {
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  padding: 9px 12px;
  border-radius: 7px;
  cursor: pointer;
}
button:hover,
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
  color: white;
}
.totals {
  padding: 18px 0;
  border-bottom: 1px solid var(--line);
  gap: 28px;
  color: var(--fg-3);
  font-size: 13px;
}
.totals b {
  color: var(--fg);
  margin-left: 8px;
}
.filters {
  display: grid;
  grid-template-columns: 2fr repeat(4, 1fr);
  gap: 14px;
  margin: 20px 0;
}
.filters label {
  font-size: 12px;
  color: var(--fg-3);
}
input:not([type='checkbox']),
select {
  display: block;
  width: 100%;
  font: inherit;
  background: var(--bg);
  color: var(--fg);
  border: 1px solid var(--line-2);
  border-radius: 7px;
  padding: 10px;
  margin-top: 7px;
}
.toolbar {
  font-size: 12px;
}
.check {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
}
.check input {
  accent-color: var(--accent);
}
.spacer {
  flex: 1;
}
.views {
  display: flex;
  gap: 5px;
}
.evidence-note {
  font-size: 12px;
  color: var(--fg-3);
  margin: 18px 0;
}
.entries.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.entry {
  border: 1px solid var(--line);
  background: var(--bg);
  border-radius: 10px;
  padding: 20px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
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
  font-size: 22px;
  line-height: 1;
  padding: 0 4px;
  border: 0;
  background: none;
}
.description {
  font-size: 13px;
  margin: 12px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 60px;
}
.badges {
  gap: 6px;
  margin: 12px 0;
}
.badges span {
  font-size: 10px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  padding: 4px 7px;
  border-radius: 5px;
}
.badges .tag {
  color: var(--accent);
}
small {
  color: var(--fg-3);
  font-size: 11px;
  line-height: 1.6;
}
.evidence {
  margin-top: auto;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.metrics div {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.metrics b {
  font-size: 15px;
}
.status {
  font-size: 11px;
  color: var(--accent);
  margin: 9px 0;
}
.warning {
  color: #e7bb72 !important;
}
.sample {
  font-size: 11px;
  margin: 7px 0;
}
.entry-actions {
  border-top: 1px solid var(--line);
  padding-top: 14px;
  margin-top: auto;
}
.entry-actions .check {
  margin-right: auto;
}
.no-run {
  font-size: 13px;
  color: var(--fg-3);
  min-height: 120px;
}
.entries.rows {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rows .entry {
  display: grid;
  grid-template-columns: minmax(230px, 1.2fr) minmax(350px, 1fr) auto;
  align-items: center;
  gap: 24px;
}
.rows .description {
  min-height: 0;
  -webkit-line-clamp: 2;
}
.rows .entry-actions {
  border: 0;
  flex-direction: column;
  padding: 0;
}
.rows .entry-actions .check {
  margin: 0;
}
.rows .evidence {
  margin: 0;
}
.empty {
  padding: 50px;
  text-align: center;
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
    font-size: 14px;
  }
  .totals {
    gap: 14px;
  }
}
</style>
