<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { AxiosInstance } from 'axios';
import { ParameterType } from '@/types/strategy';
import CodeViewer from '@/components/strategyDev/CodeViewer.vue';
import type { StrategyPreset } from '@/utils/strategyLibrary';

type Value = string | number | boolean | null;
type Field = {
  name: string;
  space: string;
  param_type: ParameterType;
  load: boolean;
  optimize: boolean;
  value: Value;
  low?: number;
  high?: number;
  decimals?: number;
  opt_range?: Value[];
};
type Schema = {
  strategy: string;
  revision: string;
  parameter_revision: string;
  schema_revision: string;
  fields: Field[];
};
const props = defineProps<{
  api: AxiosInstance;
  strategy: string;
  revision: string;
  busy: boolean;
  selected?: StrategyPreset;
}>();
const emit = defineEmits<{
  selected: [preset: StrategyPreset | undefined];
  busy: [value: boolean];
}>();
let mounted=true;
onUnmounted(()=>{mounted=false;emit('busy',false);});
const records = ref<StrategyPreset[]>([]),
  schema = ref<Schema>(),
  values = ref<Record<string, Value>>({}),
  label = ref(''),
  message = ref(''),
  bad = ref(false),
  requesting = ref(false);
const locked = computed(() => props.busy || requesting.value);
const stale = computed(
  () =>
    props.selected &&
    (props.selected.revision !== props.revision || props.selected.valid === false),
);
const selectedId = computed({
  get: () => props.selected?.id ?? '',
  set: (id: string) => {
    if (!id) emit('selected', undefined);
    else {
      const item = records.value.find((x) => x.id === id);
      if (item) emit('selected', item);
    }
  },
});
const groups = computed(() => [...new Set(schema.value?.fields.map((x) => x.space) ?? [])]);
function errorText(e: unknown) {
  const err = e as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = err.response?.data?.detail;
  return Array.isArray(detail)
    ? detail.map((x) => x.msg ?? String(x)).join('; ')
    : String(detail ?? err.message ?? e);
}
async function action(fn: () => Promise<void>) {
  requesting.value = true;
  emit('busy', true);
  bad.value = false;
  try {
    await fn();
  } catch (e) {
    message.value = errorText(e);
    bad.value = true;
  } finally {
    requesting.value = false;
    if(mounted)emit('busy', false);
  }
}
async function loadList() {
  records.value = (await props.api.get('/studio/presets/' + props.strategy)).data.presets;
}
async function inspect() {
  await action(async () => {
    schema.value = (await props.api.get('/studio/parameters/' + props.strategy)).data;
    values.value = Object.fromEntries(
      schema.value!.fields.map((field) => [field.name, field.value]),
    );
    message.value = schema.value!.fields.length
      ? 'Đã đọc tham số bằng API Freqtrade. Sửa rồi lưu thành bộ mới để sử dụng.'
      : 'Chiến lược chưa khai báo Parameter có thể nạp. Các hằng số vẫn được sửa trong tab Mã.';
  });
}
function loadSelected() {
  if (!schema.value || !props.selected) return;
  for (const field of schema.value.fields)
    if (field.load) values.value[field.name] = props.selected.values[field.name] ?? null;
  message.value = 'Đã nạp bộ đang chọn vào biểu mẫu. Lưu thành bộ mới nếu muốn thay đổi.';
}
async function save() {
  if (!schema.value) return;
  await action(async () => {
    const selectedValues = Object.fromEntries(
      schema.value!.fields.filter((x) => x.load).map((x) => [x.name, values.value[x.name]]),
    );
    const { data } = await props.api.post('/studio/presets/' + props.strategy, {
      label: label.value,
      revision: schema.value!.revision,
      parameter_revision: schema.value!.parameter_revision,
      schema_revision: schema.value!.schema_revision,
      values: selectedValues,
    });
    await loadList();
    if(mounted)emit('selected', data);
    message.value = 'Đã lưu và chọn ' + data.label + '. Chưa chạy backtest hoặc đổi bot paper.';
    label.value = '';
  });
}
async function download() {
  if (!props.selected) return;
  await action(async () => {
    const id = props.selected!.id;
    const { data } = await props.api.get(
      '/studio/presets/' + props.strategy + '/' + id + '/download',
      { responseType: 'blob' },
    );
    const url = URL.createObjectURL(data);
    const link = document.createElement('a');
    link.href = url;
    link.download = props.strategy + '-' + id.slice(0, 8) + '.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    message.value = 'Đã tải JSON tham số theo định dạng native Freqtrade.';
  });
}
function step(field: Field) {
  return field.param_type === ParameterType.IntParameter
    ? 1
    : field.decimals == null
      ? 'any'
      : 10 ** -field.decimals;
}
onMounted(() => void action(loadList));
</script>

<template>
  <section class="preset-panel" aria-label="Bộ tham số chiến lược">
    <div class="top">
      <div>
        <h3>Bộ tham số chiến lược</h3>
        <p>
          Lưu cấu hình có tên, dùng lại cho backtest và kiểm định. Hồ sơ paper kế thừa đúng tham số
          của lần backtest.
        </p>
      </div>
      <button :disabled="locked" @click="inspect">Đọc / tải lại tham số</button>
    </div>
    <label
      >Bộ đang dùng<select v-model="selectedId" :disabled="locked">
        <option value="">Từ mã và tệp tham số gốc · chưa chọn bộ riêng</option>
        <option
          v-for="item in records"
          :key="item.id"
          :value="item.id"
          :disabled="item.valid === false || item.revision !== revision"
        >
          {{ item.label }} · {{ new Date(item.created_at).toLocaleString('vi-VN')
          }}{{ item.revision !== revision ? ' · mã cũ' : ''
          }}{{ item.valid === false ? ' · tệp không khớp' : '' }}
        </option>
      </select></label
    >
    <p v-if="stale" class="notice bad">
      Bộ đang chọn không khớp mã hiện tại hoặc tệp đã đổi. Chọn bộ hợp lệ hay giá trị gốc trước khi
      chạy.
    </p>
    <div v-if="selected" class="selected">
      <span
        ><b>{{ selected.label }}</b> · mã {{ selected.revision.slice(0, 10) }} ·
        {{ Object.keys(selected.values).length }} tham số</span
      ><button :disabled="locked || selected.valid === false" @click="download">
        Tải JSON native
      </button>
      <details>
        <summary>Xem giá trị đã lưu</summary>
        <CodeViewer :code="JSON.stringify(selected.values, null, 2)" language="json" />
      </details>
    </div>
    <p v-if="message" class="notice" :class="{ bad }" role="status">{{ message }}</p>
    <details v-if="schema" open>
      <summary>Chuẩn bị bộ tham số mới</summary>
      <p>
        Giới hạn lấy từ khai báo Parameter gốc. Chỉ sửa giá trị cố định; không chạy tối ưu. Thay đổi
        biểu mẫu chỉ được dùng sau khi lưu và chọn bộ mới.
      </p>
      <p v-if="schema.revision !== revision" class="notice bad">
        Mã đã đổi sau khi đọc tham số. Đọc lại trước khi lưu.
      </p>
      <button
        v-if="selected"
        :disabled="locked || stale || schema.revision !== revision"
        @click="loadSelected"
      >
        Nạp bộ đang chọn vào biểu mẫu
      </button>
      <fieldset v-for="group in groups" :key="group">
        <legend>{{ group }}</legend>
        <div class="fields">
          <label v-for="field in schema.fields.filter((x) => x.space === group)" :key="field.name"
            ><b>{{ field.name }}</b
            ><select
              v-if="field.opt_range"
              v-model="values[field.name]"
              :disabled="locked || !field.load"
            >
              <option v-for="(choice, index) in field.opt_range" :key="index" :value="choice">
                {{
                  typeof choice === 'boolean' ? (choice ? 'Có (true)' : 'Không (false)') : choice
                }}
              </option></select
            ><input
              v-else
              v-model.number="values[field.name]"
              type="number"
              :min="field.low"
              :max="field.high"
              :step="step(field)"
              :disabled="locked || !field.load"
            /><small
              >{{ field.param_type
              }}<template v-if="field.low != null"> · {{ field.low }}–{{ field.high }}</template
              >{{ field.decimals == null ? '' : ' · ' + field.decimals + ' chữ số thập phân'
              }}{{ field.load ? '' : ' · load=false, giữ nguyên' }}</small
            ></label
          >
        </div>
      </fieldset>
      <div v-if="schema.fields.some((x) => x.load)" class="save-row">
        <label
          >Tên bộ mới<input
            v-model="label"
            maxlength="70"
            placeholder="Ví dụ: Cấu hình gốc để đối chiếu"
            :disabled="locked" /></label
        ><button
          class="primary"
          :disabled="locked || !label.trim() || schema.revision !== revision"
          @click="save"
        >
          Lưu thành bộ mới và chọn
        </button>
      </div>
    </details>
    <small class="scope"
      >Bộ riêng chỉ được sao chép vào hồ sơ của lần chạy. Không ghi đè .py/.json trong thư viện,
      không đổi vốn/ngày/phí ở biểu mẫu bên dưới và không tự bật paper. ROI/stoploss/trailing trong
      tệp tham số gốc, nếu có, được giữ nguyên khi tạo bộ mới.</small
    >
  </section>
</template>

<style scoped>
.preset-panel {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 20px;
  margin: 18px 0 26px;
  color: var(--fg);
}
.top,
.selected,
.save-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.top {
  justify-content: space-between;
}
.top h3 {
  margin: 0;
  font-size: 18px;
}
.top p {
  margin: 8px 0 16px;
}
p {
  font-size: 13px;
  color: var(--fg-2);
  line-height: 1.6;
  text-align: left;
}
label {
  display: block;
  font-size: 12px;
  color: var(--fg-2);
  margin: 12px 0;
  text-align: left;
}
input,
select {
  display: block;
  width: 100%;
  font: inherit;
  margin-top: 7px;
  padding: 10px;
  color: var(--fg);
  background: var(--bg);
  border: 1px solid var(--line-2);
  border-radius: 7px;
}
button {
  font: inherit;
  font-size: 12px;
  padding: 9px 12px;
  border: 1px solid var(--line-2);
  border-radius: 7px;
  background: var(--bg-2);
  color: var(--fg);
  cursor: pointer;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
.primary {
  background: #1b6a5c;
  color: white;
}
.notice {
  border-left: 3px solid var(--accent);
  background: #132b2a;
  padding: 12px;
  margin: 14px 0;
}
.bad {
  border-color: #ee8989;
  background: #3c2024;
  color: #ffb4b4;
}
.selected {
  font-size: 12px;
  margin: 14px 0;
}
.selected details {
  width: 100%;
}
details {
  margin: 16px 0;
}
summary {
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
}
.fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
fieldset {
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 12px 16px;
  margin: 14px 0;
}
legend {
  font-size: 12px;
  color: var(--accent);
}
small {
  display: block;
  font-size: 11px;
  color: var(--fg-3);
  line-height: 1.6;
  text-align: left;
  margin-top: 7px;
}
.scope {
  margin-top: 18px;
}
.save-row label {
  flex: 1;
  min-width: 220px;
}
@media (max-width: 900px) {
  .fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 650px) {
  .fields {
    grid-template-columns: 1fr;
  }
  .preset-panel {
    padding: 14px;
  }
}
</style>
