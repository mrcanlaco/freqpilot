// Public projection of benchmarks/scanned-strategies-summary.json → protocol_10k_audit.
// runId identifies the backtest. sha identifies its archived ZIP. walkId identifies a separate job.
const PUBLIC_RUNS = {
  "DikibagastEmaRsi1h": {
    "rev": "b82e4ae101e57e49d60259b0a8bd9563ff9649a013899ecf37b71bc458a760ce",
    "runId": "b9f8eb39c3",
    "sha": "355afab9d5883dd75cb59fa0bf3ff262381e22ad0d1a5e6e347cccaabe428f25",
    "period": "20260401-20261021",
    "detail": "5m",
    "walkId": "3215a26798d5424db99191b3e6e14296"
  },
  "RocketHunterSma501h": {
    "rev": "484cebfefabdb02966797488d23a0fbd17011a1000b1e87d0d1dbed791ef8613",
    "runId": "fd368e3110",
    "sha": "a97bd2aa06dc9820f0abbe9994753e6dda4bb65ac8a4018bf93c78118ee27a83",
    "period": "20260401-20261021",
    "detail": "5m",
    "walkId": null
  },
  "TarsisVolTargetSma501h": {
    "rev": "71d5550cb1bb7719141356ea5c5eb6fdc518f46a66ad4021f6a4528c2bb9d474",
    "runId": "f29c4c1d9a",
    "sha": "d3a223a86af423d589d9ec11908a4f979e01089eed9ac5da85ee31462dead0ff",
    "period": "20260401-20261021",
    "detail": "5m",
    "walkId": null
  },
  "BdrEmaRideFutures1h": {
    "rev": "1474053fd71fadb635b0018eb1ea2c1cfd3c96411f1fa6410132b18eefdd4896",
    "runId": "92ea977e05",
    "sha": "9ab6887c4d2256d11fb17d47135e4912f3dae4074e29fc1670f529530caac13d",
    "period": "20260401-20261021",
    "detail": "5m",
    "walkId": null
  },
  "TrendCoreBagging1h": {
    "rev": "f1260f2655d0d1cec9988811ac867acd4f43be0f46528d826ff5d64e1c3ea855",
    "runId": "b0692cd1ca",
    "sha": "2c5d5ff39e7212a534a98ba3ff22a26a3a7f2ad00547a6b6680f59fbc8c0eacc",
    "period": "20260401-20261021",
    "detail": "5m",
    "walkId": null
  },
  "CodexBotVibe4h": {
    "rev": "c1e250bee2ccd79fcf65292247ccc624ca6827bee2f454c77fa84859c09981cb",
    "runId": "916aad1ea4",
    "sha": "2ae3b88a63f1933cfb714fe86461f225b3fd06a618effab704e1bfc1eaa6dbad",
    "period": "20260401-20261021",
    "detail": "5m",
    "walkId": null
  },
  "StarterFuturesResearch": {
    "rev": "b336e80227ea8a39d13f0592c2dd97496f130d0a7135f09c71095c1d97bb3fe6",
    "runId": "813a9807e1",
    "sha": "44ac8d16221b0a9dd7b703f00f1bdd96c2d5a92bdd899cac0a58352044ef3fa2",
    "period": "20260918-20261021",
    "detail": "1m",
    "walkId": null
  }
};

const WALK_FORWARD = [
  {
    "id": "3215a26798d5424db99191b3e6e14296",
    "strategy": "DikibagastEmaRsi1h",
    "rev": "b82e4ae101e57e49d60259b0a8bd9563ff9649a013899ecf37b71bc458a760ce",
    "runId": "b9f8eb39c3",
    "sha": "355afab9d5883dd75cb59fa0bf3ff262381e22ad0d1a5e6e347cccaabe428f25",
    "holdout": "20260916-20261021",
    "windows": [
      {
        "index": 0,
        "train_timerange": "20260401-20260630",
        "oos_timerange": "20260630-20260804",
        "baseline_pnl": -70.72001386,
        "baseline_trades": 4,
        "candidate_pnl": -6.046134639999998,
        "candidate_trades": 3
      },
      {
        "index": 1,
        "train_timerange": "20260506-20260804",
        "oos_timerange": "20260804-20260908",
        "baseline_pnl": 141.6116249,
        "baseline_trades": 11,
        "candidate_pnl": 105.83095663,
        "candidate_trades": 10
      }
    ],
    "baseline": {
      "total_trades": 5,
      "profit_total_abs": 94.44092562,
      "profit_factor": 3.2881878269168467,
      "max_drawdown_account": 0.004113204278431726
    },
    "candidate": {
      "total_trades": 3,
      "profit_total_abs": -50.849532839999995,
      "profit_factor": 0.3522963133091203,
      "max_drawdown_account": 0.007829086482092764
    }
  }
];

const WALK_COPY = {
  vi: { missing: "Chưa có kết quả", job: "Lần kiểm định", baseline: "Tham số gốc", candidate: "Ứng viên Hyperopt", trades: "lệnh", source: "Xem nguồn kiểm định", train: "Huấn luyện", holdout: "Kỳ giữ lại" },
  en: { missing: "No results yet", job: "Validation run", baseline: "Untuned baseline", candidate: "Hyperopt candidate", trades: "trades", source: "View validation source", train: "Training", holdout: "Holdout" },
  zh: { missing: "暂无结果", job: "验证运行", baseline: "原始参数", candidate: "Hyperopt 候选", trades: "笔交易", source: "查看验证来源", train: "训练", holdout: "留出期" },
  ru: { missing: "Пока нет результатов", job: "Проверка", baseline: "Исходные параметры", candidate: "Кандидат Hyperopt", trades: "сделок", source: "Источник проверки", train: "Обучение", holdout: "Отложенный период" },
  ko: { missing: "아직 결과가 없습니다", job: "검증 실행", baseline: "기본 매개변수", candidate: "Hyperopt 후보", trades: "거래", source: "검증 출처 보기", train: "학습", holdout: "홀드아웃" }
};

const STARTER_WHOP_URL = "https://whop.com/freqpilot/freqpilot-free-starter-bundle-sha-256-verified/";

function walkForwardFor(strategy) {
  return WALK_FORWARD.find(w => w.strategy === strategy.id && w.rev === strategy.rev
    && w.runId === strategy.runId && w.sha === strategy.sha && w.id === strategy.walkId);
}

function formatRange(range) {
  return range.split("-").map(date => date.replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3")).join(" → ");
}

// Keep explicit links usable across reloads and when browser storage is unavailable.
function updateLanguageLinks(lang) {
  const current = new URL(location.href);
  if (current.searchParams.has("lang") && current.searchParams.get("lang") !== lang) {
    current.searchParams.set("lang", lang);
    history.replaceState(null, "", current);
  }
  document.querySelectorAll('a[href^="/"]').forEach(link => {
    const url = new URL(link.href);
    if (url.origin !== location.origin || !["/", "/demo", "/demo.html", "/compare.html"].includes(url.pathname)) return;
    url.searchParams.set("lang", lang);
    link.setAttribute("href", url.pathname + url.search + url.hash);
  });
}

function walkForwardPanel(strategy, lang) {
  const t = WALK_COPY[lang];
  const w = walkForwardFor(strategy);
  const heading = `<h3>Walk-forward · ${strategy.id}</h3>`;
  if (!w) return heading + `<p>${t.missing}</p>`;
  const money = n => n.toLocaleString(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "always" });
  const result = (pnl, trades) => `<b class="${pnl < 0 ? "neg" : "pos"}">${money(pnl)} USDT</b> · ${trades} ${t.trades}`;
  const outcome = s => `${result(s.profit_total_abs, s.total_trades)} · PF ${s.profit_factor.toFixed(2)} · DD ${(100 * s.max_drawdown_account).toFixed(2)}%`;
  return heading + `
    <p>${t.job} <code title="${w.id}">${w.id.slice(0, 10)}</code> · rev <code>${w.rev.slice(0, 10)}</code></p>
    <h4>${t.holdout} · ${formatRange(w.holdout)}</h4>
    <p>${t.baseline} · ${outcome(w.baseline)}<br>${t.candidate} · ${outcome(w.candidate)}</p>
    ${w.windows.map(row => `<details><summary>OOS #${row.index} · ${formatRange(row.oos_timerange)}</summary>
      <p>${t.train} · ${formatRange(row.train_timerange)}<br>
      ${t.baseline} · ${result(row.baseline_pnl, row.baseline_trades)}<br>
      ${t.candidate} · ${result(row.candidate_pnl, row.candidate_trades)}</p></details>`).join("")}
    <p><a href="https://github.com/mrcanlaco/freqpilot/blob/main/benchmarks/scanned-strategies-summary.json">${t.source} ↗</a></p>`;
}
