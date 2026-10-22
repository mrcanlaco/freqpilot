<script setup lang="ts">
defineProps<{phase:string;attempt:number;maxAttempts:number;error:string;hasBots:boolean}>();
defineEmits<{retry:[];settings:[]}>();
</script>
<template>
  <section class="connection" aria-label="Kết nối nghiên cứu">
    <h2>{{phase==='loading'||phase==='idle'?'Đang kết nối nghiên cứu':phase==='waiting'?'Đang chờ dịch vụ nghiên cứu':'Chưa kết nối được dịch vụ nghiên cứu'}}</h2>
    <p v-if="phase==='loading'||phase==='idle'" role="status">Đang đọc trạng thái và kiểm tra workspace FreqPilot · lần {{attempt||1}}/{{maxAttempts}}.</p>
    <p v-if="error" role="status">{{error}}</p>
    <p v-if="phase==='waiting'">Sẽ tự thử lại · tối đa {{maxAttempts}} lần.</p>
    <p v-else-if="phase==='failed'&&hasBots">Khi dịch vụ đã sẵn sàng, thử kết nối lại ngay tại đây. Với phiên đăng nhập hết hạn, mở cài đặt kết nối.</p>
    <p v-else-if="!hasBots">Thêm Backtest tại http://localhost:8091 bằng tài khoản local hiện có.</p>
    <div class="actions"><button v-if="hasBots" class="primary" :disabled="phase==='loading'||phase==='idle'" @click="$emit('retry')">Thử kết nối lại</button><button @click="$emit('settings')">Mở cài đặt kết nối</button></div>
  </section>
</template>
<style scoped>
.connection{border:1px solid var(--line);border-radius:12px;background:var(--bg-1);padding:28px;text-align:left;max-width:850px;margin:24px auto}h2{font-size:22px;margin:0 0 16px}p{color:var(--fg-2);line-height:1.6}.actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}button{font:inherit;font-size:13px;border:1px solid var(--line-2);border-radius:7px;padding:10px 14px;color:var(--fg);background:var(--bg-2);cursor:pointer}button:disabled{opacity:.4;cursor:default}.primary{background:#1b6a5c;color:#f2fff9;border-color:#268b77}
</style>
