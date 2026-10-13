/* Workforce Story: renders app/data/metrics.json (built by `python -m metrics.build`). */
(() => {
  "use strict";

  const SERIES = {
    light: ["#2a78d6", "#eb6834", "#1baf7a"],
    dark: ["#3987e5", "#d95926", "#199e70"],
  };
  const GROUPS = [["all", "Everyone"], ["clinical", "Clinical"], ["nonclinical", "Non-clinical"]];
  const state = { fy: 2026, group: "all", data: null, charts: [] };
  const $ = (s, el = document) => el.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const isDark = () => document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const color = (i) => SERIES[isDark() ? "dark" : "light"][i];

  // ---------------------------------------------------------------- formatting
  const nf = new Intl.NumberFormat("en-US");
  const fmt = {
    int: (v) => v == null ? "–" : nf.format(Math.round(v)),
    pct: (v, d = 1) => v == null ? "–" : `${Number(v).toFixed(d)}%`,
    pct2: (v) => fmt.pct(v, 2),
    days: (v) => v == null ? "–" : `${Number(v).toFixed(1)} days`,
    hours: (v) => v == null ? "–" : `${Number(v).toFixed(1)} hrs`,
    money: (v) => v == null ? "–" : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${nf.format(Math.round(v))}`,
    ratio: (v) => v == null ? "–" : Number(v).toFixed(3),
    rate: (v) => v == null ? "–" : `$${Number(v).toFixed(2)}/hr`,
  };
  const monthLabel = (m) => new Date(`${m}-15`).toLocaleDateString("en-US", { month: "short", year: "numeric" });
  const fyOf = (m) => (+m.slice(5, 7) >= 10 ? +m.slice(0, 4) + 1 : +m.slice(0, 4));

  // ---------------------------------------------------------------- chart plumbing
  const tip = $("#tip");
  function externalTooltip(valueFmt) {
    return (ctx) => {
      const t = ctx.tooltip;
      if (!t || t.opacity === 0) { tip.hidden = true; return; }
      tip.replaceChildren();
      const title = document.createElement("div");
      title.className = "t";
      title.textContent = (t.title || []).join(" ");
      tip.append(title);
      for (const dp of t.dataPoints || []) {
        const row = document.createElement("div");
        row.className = "row";
        const key = document.createElement("i");
        const bc = dp.dataset.borderColor || dp.dataset.backgroundColor;
        key.style.background = Array.isArray(bc) ? bc[dp.dataIndex] : bc;
        const val = document.createElement("b");
        val.textContent = (dp.dataset.fmt || valueFmt)(dp.raw);
        const name = document.createElement("span");
        name.textContent = dp.dataset.label;
        row.append(key, val, name);
        tip.append(row);
      }
      const r = ctx.chart.canvas.getBoundingClientRect();
      tip.hidden = false;
      const w = tip.offsetWidth, h = tip.offsetHeight;
      let x = r.left + t.caretX + 14, y = r.top + t.caretY - h / 2;
      if (x + w > innerWidth - 8) x = r.left + t.caretX - w - 14;
      tip.style.left = `${Math.max(8, x)}px`;
      tip.style.top = `${Math.min(innerHeight - h - 8, Math.max(8, y))}px`;
    };
  }

  // shades the selected fiscal year and marks story events on monthly charts
  const timePlugin = {
    id: "timeContext",
    beforeDatasetsDraw(chart, _a, opts) {
      if (!opts || !opts.months) return;
      const { ctx, chartArea: area, scales: { x } } = chart;
      const idx = opts.months.map((m, i) => (fyOf(m) === state.fy ? i : -1)).filter((i) => i >= 0);
      if (idx.length) {
        const step = (x.getPixelForValue(1) - x.getPixelForValue(0)) || 0;
        const left = x.getPixelForValue(idx[0]) - step / 2, right = x.getPixelForValue(idx[idx.length - 1]) + step / 2;
        ctx.save();
        ctx.fillStyle = css("--accent-wash");
        ctx.globalAlpha = isDark() ? 0.55 : 0.75;
        ctx.fillRect(Math.max(area.left, left), area.top, Math.min(area.right, right) - Math.max(area.left, left), area.bottom - area.top);
        ctx.restore();
      }
    },
    afterDatasetsDraw(chart, _a, opts) {
      if (!opts || !opts.months || !opts.events) return;
      const { ctx, chartArea: area, scales: { x } } = chart;
      ctx.save();
      ctx.strokeStyle = css("--muted");
      ctx.fillStyle = css("--ink-2");
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.font = `500 12px ${css("--font")}`;
      state.data.meta.events.forEach((ev, k) => {
        const i = opts.months.findIndex((m) => m.slice(0, 7) === ev.date);
        if (i < 0) return;
        const px = x.getPixelForValue(i);
        ctx.beginPath(); ctx.moveTo(px, area.top); ctx.lineTo(px, area.bottom); ctx.stroke();
        if (opts.labels !== false && area.right - area.left > 560) {
          const label = ev.label;
          const w = ctx.measureText(label).width;
          const lx = px + w + 8 > area.right ? px - w - 6 : px + 5;
          ctx.fillText(label, lx, area.top + 12 + (k % 4) * 15);
        }
      });
      ctx.restore();
    },
  };

  const crosshair = {
    id: "crosshair",
    afterDraw(chart) {
      if (chart.config.type !== "line") return;
      const a = chart.tooltip && chart.tooltip.getActiveElements();
      if (!a || !a.length) return;
      const { ctx, chartArea: area } = chart;
      ctx.save();
      ctx.strokeStyle = css("--rule-strong");
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(a[0].element.x, area.top); ctx.lineTo(a[0].element.x, area.bottom); ctx.stroke();
      ctx.restore();
    },
  };

  function makeChart(canvas, spec) {
    const grid = css("--rule"), ink = css("--muted");
    const horizontal = !!spec.horizontal;
    const datasets = spec.datasets.map((d, i) => {
      const c = color(d.color ?? i);
      return spec.type === "line"
        ? { label: d.label, data: d.data, fmt: d.fmt, borderColor: c, backgroundColor: c, borderWidth: 2, pointRadius: 0,
            pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: css("--surface"), tension: 0.25, spanGaps: true }
        : { label: d.label, data: d.data, fmt: d.fmt, backgroundColor: spec.barColors ? spec.barColors.map(color) : c,
            borderColor: spec.barColors ? spec.barColors.map(color) : c, borderRadius: 4,
            borderSkipped: "start", maxBarThickness: horizontal ? 18 : 26, categoryPercentage: 0.78, barPercentage: 0.9,
            hoverBackgroundColor: spec.barColors ? spec.barColors.map((k) => color(k) + "cc") : c + "cc" };
    });
    const valueAxis = {
      beginAtZero: spec.type === "bar" || spec.zero, grid: { color: grid, drawTicks: false }, border: { display: false },
      ticks: { color: ink, padding: 8, maxTicksLimit: 5, font: { size: 12 }, callback: (v) => (spec.tick || spec.fmt)(v) },
      suggestedMin: spec.min, suggestedMax: spec.max,
    };
    const catAxis = {
      grid: { display: false }, border: { color: css("--rule-strong") },
      ticks: { color: ink, font: { size: 12 }, autoSkip: !horizontal, maxRotation: 0,
               maxTicksLimit: spec.months ? 7 : undefined,
               callback(v) { const l = this.getLabelForValue(v); return spec.months ? monthLabel(l.slice(0, 7)) : l; } },
    };
    return new Chart(canvas, {
      type: spec.type,
      data: { labels: spec.labels, datasets },
      plugins: [timePlugin, crosshair],
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 }, indexAxis: horizontal ? "y" : "x",
        interaction: { mode: "index", intersect: false, axis: horizontal ? "y" : "x" },
        layout: { padding: { top: spec.months && spec.eventLabels !== false ? 4 : 0, right: 6 } },
        scales: horizontal ? { x: valueAxis, y: catAxis } : { x: catAxis, y: valueAxis },
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false, external: externalTooltip(spec.fmt),
                     callbacks: { title: (items) => items.length ? (spec.months ? monthLabel(items[0].label.slice(0, 7)) +
                       (items[0].label.length > 7 ? ` (check ${items[0].label})` : "") : items[0].label) : "" } },
          timeContext: spec.months ? { months: spec.months, events: spec.events, labels: spec.eventLabels } : false,
        },
      },
    });
  }

  function figure(spec) {
    const fig = document.createElement("figure");
    fig.className = `chart${spec.wide ? " wide" : ""}${spec.short ? " short" : ""}`;
    const head = document.createElement("div");
    const h = document.createElement("h3"); h.textContent = spec.title;
    head.append(h);
    if (spec.sub) { const s = document.createElement("p"); s.className = "sub"; s.textContent = spec.sub; head.append(s); }
    const wrap = document.createElement("div"); wrap.className = "canvas";
    if (spec.horizontal) wrap.style.height = `${Math.max(150, spec.labels.length * 30 + 44)}px`;
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `${spec.title}. Use Show data for the values.`);
    wrap.append(canvas);
    const foot = document.createElement("div"); foot.className = "chart-foot";
    const legend = document.createElement("ul"); legend.className = "legend";
    if (spec.legendItems) {
      spec.legendItems.forEach(([label, k]) => {
        const li = document.createElement("li"); const key = document.createElement("i");
        key.style.background = color(k); li.append(key, document.createTextNode(label)); legend.append(li);
      });
    } else if (spec.datasets.length > 1 || spec.events) {
      spec.datasets.forEach((d, i) => {
        const li = document.createElement("li"); const k = document.createElement("i");
        if (spec.type === "line") k.className = "line";
        k.style.background = color(d.color ?? i);
        li.append(k, document.createTextNode(d.label)); legend.append(li);
      });
      if (spec.events) {
        const li = document.createElement("li"); const k = document.createElement("i"); k.className = "event";
        li.append(k, document.createTextNode("Event")); legend.append(li);
      }
      if (spec.months) {
        const li = document.createElement("li"); const k = document.createElement("i");
        k.style.background = css("--accent-wash"); k.style.outline = `1px solid ${css("--rule-strong")}`;
        li.append(k, document.createTextNode(`FY${state.fy % 100}`)); legend.append(li);
      }
    }
    const btn = document.createElement("button"); btn.type = "button"; btn.className = "table-btn"; btn.textContent = "Show data";
    btn.setAttribute("aria-expanded", "false");
    foot.append(legend, btn);
    const table = document.createElement("div"); table.className = "data-table"; table.hidden = true;
    btn.addEventListener("click", () => {
      const open = table.hidden;
      if (open && !table.firstChild) table.append(buildTable(spec));
      table.hidden = !open; wrap.hidden = open;
      btn.textContent = open ? "Show chart" : "Show data";
      btn.setAttribute("aria-expanded", String(open));
    });
    fig.append(head, wrap, table, foot);
    return { fig, canvas };
  }

  function buildTable(spec) {
    const t = document.createElement("table");
    const tr = document.createElement("tr");
    const th0 = document.createElement("th"); th0.textContent = spec.category || (spec.months ? "Period" : "Category");
    tr.append(th0);
    spec.datasets.forEach((d) => { const th = document.createElement("th"); th.className = "num"; th.textContent = d.label; tr.append(th); });
    const thead = document.createElement("thead"); thead.append(tr);
    const tbody = document.createElement("tbody");
    spec.labels.forEach((l, i) => {
      const r = document.createElement("tr");
      const td0 = document.createElement("td"); td0.textContent = spec.months && l.length === 7 ? monthLabel(l) : l; r.append(td0);
      spec.datasets.forEach((d) => { const td = document.createElement("td"); td.className = "num"; td.textContent = (d.fmt || spec.fmt)(d.data[i]); r.append(td); });
      tbody.append(r);
    });
    t.append(thead, tbody);
    return t;
  }

  // ---------------------------------------------------------------- chapters
  const delta = (cur, prev, unit = "pts", digits = 1) => {
    if (prev == null || cur == null) return "";
    const d = cur - prev;
    const s = Math.abs(d).toFixed(digits);
    return d === 0 ? "No change" : `${d > 0 ? "Up" : "Down"} ${s} ${unit} vs FY${(state.fy - 1) % 100}`;
  };

  const byGross = (s) => [...s.payroll_by_dept].sort((a, b) => b.gross_pay_usd - a.gross_pay_usd).slice(0, 10);
  const byOT = (s) => [...s.payroll_by_dept].sort((a, b) => b.overtime_pay_usd - a.overtime_pay_usd).slice(0, 10);

  const CHAPTERS = [
    {
      id: "enterprise", name: "The enterprise", story: "enterprise",
      kpis: (s) => [
        [fmt.int(s.enterprise.average_headcount), "Average headcount"],
        [fmt.int(s.enterprise.fte_end), "FTEs at year end"],
        [fmt.money(s.enterprise.gross_payroll_usd), "Gross payroll"],
        [fmt.money(s.enterprise.labor_cost_per_fte_usd), "Payroll cost per FTE"],
      ],
      charts: (s, ser) => [
        { type: "bar", wide: true, title: "Hires and departures by month", sub: "Every month, the system replaces roughly 80 to 100 people.",
          labels: ser.headcount.map((r) => r.month), months: ser.headcount.map((r) => r.month), events: true, fmt: fmt.int,
          datasets: [{ label: "Hires", data: ser.headcount.map((r) => r.hires) }, { label: "Departures", data: ser.headcount.map((r) => r.terminations) }] },
        { type: "bar", horizontal: true, title: "Where the payroll goes", sub: `Gross pay by department, top 10, FY${state.fy % 100}`, category: "Department",
          labels: byGross(s).map((r) => r.dept_name), fmt: fmt.money,
          datasets: [{ label: "Gross pay", data: byGross(s).map((r) => r.gross_pay_usd) }] },
        { type: "bar", horizontal: true, title: "Turnover by job family", sub: `Share of average headcount who left, FY${state.fy % 100}`, category: "Job family",
          labels: s.turnover_by_family.map((r) => r.job_family), fmt: fmt.pct,
          datasets: [{ label: "Turnover rate", data: s.turnover_by_family.map((r) => r.turnover_rate_pct) }] },
      ],
    },
    {
      id: "talent", name: "Talent acquisition", story: "talent",
      kpis: (s, p) => [
        [fmt.int(s.recruiting.requisitions_filled), "Requisitions filled"],
        [fmt.days(s.recruiting.avg_days_to_fill), p ? delta(s.recruiting.avg_days_to_fill, p.recruiting.avg_days_to_fill, "days") : "Average days to fill"],
        [fmt.pct(s.recruiting.offer_acceptance_rate_pct), "Offer acceptance rate"],
        [fmt.pct(s.recruiting.vacancy_rate_pct), `Vacancy rate, ${fmt.int(s.recruiting.open_requisitions_at_year_end)} open roles at year end`],
      ],
      charts: (s, ser) => {
        const months = ser.days_to_fill_all.map((r) => r.month);
        const nurse = Object.fromEntries(ser.days_to_fill_nursing.map((r) => [r.month, r.avg_days_to_fill]));
        const ds = [{ label: "All roles", data: ser.days_to_fill_all.map((r) => r.avg_days_to_fill) }];
        if (ser.days_to_fill_nursing.length) ds.push({ label: "Nursing", data: months.map((m) => nurse[m] ?? null) });
        return [
          { type: "line", wide: true, title: "Days to fill, by month of acceptance", sub: "Nursing searches stretched while a competitor was recruiting, then recovered after the market adjustment.",
            labels: months, months, events: true, fmt: fmt.days, tick: (v) => `${v}`, datasets: ds },
          { type: "bar", horizontal: true, title: "Recruiting funnel", sub: `Candidates on requisitions filled in FY${state.fy % 100}`, category: "Stage",
            labels: s.funnel.map((r) => r.stage), fmt: fmt.int,
            datasets: [{ label: "Candidates", data: s.funnel.map((r) => r.count) }] },
          { type: "bar", horizontal: true, title: "Days to fill by job family", sub: "Families with at least five fills", category: "Job family",
            labels: s.recruiting_by_family.map((r) => r.job_family), fmt: fmt.days, tick: (v) => `${v}`,
            datasets: [{ label: "Average days to fill", data: s.recruiting_by_family.map((r) => r.avg_days_to_fill) }] },
          { type: "bar", horizontal: true, wide: true, short: true, title: "Where hires came from", sub: `Source of hire, FY${state.fy % 100}`, category: "Source",
            labels: s.sources.map((r) => r.source_of_hire), fmt: fmt.pct,
            datasets: [{ label: "Share of hires", data: s.sources.map((r) => r.share_pct) }] },
        ];
      },
    },
    {
      id: "retention", name: "Retention", story: "retention",
      kpis: (s, p) => [
        [fmt.pct(s.retention.turnover_rate_pct), p ? delta(s.retention.turnover_rate_pct, p.retention.turnover_rate_pct) : "Turnover rate"],
        [fmt.pct(s.retention.voluntary_turnover_rate_pct), "Voluntary turnover"],
        [fmt.pct(s.retention.early_turnover_share_pct), "Of departures had under a year of tenure"],
        [fmt.pct(s.retention.retention_rate_pct), "Of the people here on Oct 1 were still here Sep 30"],
      ],
      charts: (s, ser) => {
        const months = ser.turnover_all.map((r) => r.month);
        const ds = [{ label: "All staff", data: ser.turnover_all.map((r) => r.annualized_turnover_pct) }];
        if (ser.turnover_nursing.length) ds.push({ label: "Nursing", data: ser.turnover_nursing.map((r) => r.annualized_turnover_pct) });
        return [
          { type: "line", wide: true, title: "Annualized turnover by month", sub: "Monthly departures divided by headcount, times twelve.",
            labels: months, months, events: true, fmt: fmt.pct, tick: (v) => `${v}%`, zero: true, datasets: ds },
          { type: "bar", horizontal: true, title: "When people leave", sub: `Departures by tenure at exit, FY${state.fy % 100}`, category: "Tenure",
            labels: s.turnover_by_tenure.map((r) => r.tenure_band), fmt: fmt.int,
            datasets: [{ label: "Departures", data: s.turnover_by_tenure.map((r) => r.terminations) }] },
          { type: "bar", horizontal: true, title: "Why people leave", sub: `Top reasons, FY${state.fy % 100}`, category: "Reason",
            labels: s.turnover_by_reason.map((r) => r.term_reason), fmt: fmt.int,
            datasets: [{ label: "Departures", data: s.turnover_by_reason.map((r) => r.terminations) }] },
        ];
      },
    },
    {
      id: "payroll", name: "Payroll", story: "payroll",
      kpis: (s, p) => [
        [fmt.money(s.payroll.gross_pay_usd), `Gross pay across ${s.payroll.pay_periods} pay periods`],
        [fmt.money(s.payroll.overtime_pay_usd), "Overtime pay"],
        [fmt.pct2(s.payroll.overtime_rate_pct), p ? delta(s.payroll.overtime_rate_pct, p.payroll.overtime_rate_pct, "pts", 2) : "Overtime hours / regular hours"],
        [fmt.int(s.payroll.off_cycle_corrections), `Off-cycle corrections, ${s.payroll.corrections_per_1000_checks} per 1,000 checks`],
      ],
      charts: (s, ser) => {
        const p = ser.payroll;
        const months = p.map((r) => r.check_date.slice(0, 7));
        return [
          { type: "line", wide: true, title: "Overtime rate by pay period", sub: "Nonexempt overtime hours as a share of regular hours. Vacancies turn into overtime.",
            labels: p.map((r) => r.check_date), months, events: true, fmt: fmt.pct2, tick: (v) => `${v}%`,
            datasets: [{ label: "Overtime rate", data: p.map((r) => r.overtime_rate_pct) }] },
          { type: "line", title: "Off-cycle corrections per 1,000 checks", sub: "The February 2025 payroll upgrade shows up here first.",
            labels: p.map((r) => r.check_date), months, events: true, eventLabels: false, fmt: (v) => v == null ? "–" : Number(v).toFixed(1), zero: true,
            datasets: [{ label: "Corrections per 1,000 checks", data: p.map((r) => r.corrections_per_1000_checks) }] },
          { type: "bar", horizontal: true, title: "Overtime pay by department", sub: `Top 10, FY${state.fy % 100}`, category: "Department",
            labels: byOT(s).map((r) => r.dept_name), fmt: fmt.money,
            datasets: [{ label: "Overtime pay", data: byOT(s).map((r) => r.overtime_pay_usd) }] },
        ];
      },
    },
    {
      id: "services", name: "HR services", story: "services",
      kpis: (s, p) => [
        [fmt.int(s.service.cases_opened), `Cases opened, ${s.service.cases_per_100_employees} per 100 employees`],
        [fmt.pct(s.service.sla_met_rate_pct), p ? delta(s.service.sla_met_rate_pct, p.service.sla_met_rate_pct) : "Resolved within SLA"],
        [fmt.hours(s.service.median_resolution_hours), "Median time to resolve"],
        [fmt.pct(s.service.first_contact_resolution_pct), "Tier 1 resolved on first contact"],
      ],
      charts: (s, ser) => {
        const c = ser.cases, months = c.map((r) => r.month);
        return [
          { type: "line", wide: true, title: "Cases opened per month", sub: "Open enrollment every November, tax forms every January, and the payroll upgrade in early 2025.",
            labels: months, months, events: true, fmt: fmt.int, zero: true,
            datasets: [{ label: "All cases", data: c.map((r) => r.total) }, { label: "Payroll cases", data: c.map((r) => r.Payroll || 0) }] },
          { type: "line", title: "Median time to route a case", sub: "Hours from case opened to assigned. AI-assisted triage launched in October 2025.",
            labels: months, months, events: true, eventLabels: false, fmt: fmt.hours, tick: (v) => `${v}h`, zero: true,
            datasets: [{ label: "Median hours to assign", data: c.map((r) => r.median_hours_to_assign) }] },
          { type: "bar", horizontal: true, title: "Cases by category", sub: `FY${state.fy % 100}`, category: "Category",
            labels: s.service_by_category.map((r) => r.category), fmt: fmt.int,
            datasets: [{ label: "Cases", data: s.service_by_category.map((r) => r.cases) }] },
        ];
      },
    },
    {
      id: "compensation", name: "Compensation", story: "compensation",
      kpis: (s) => [
        [fmt.ratio(s.compensation.avg_compa_ratio), "Average compa-ratio (pay ÷ range midpoint)"],
        [fmt.pct(s.compensation.below_range_midpoint_pct), "Paid below range midpoint"],
        [s.compensation.avg_merit_increase_pct == null ? "None" : fmt.pct2(s.compensation.avg_merit_increase_pct),
         s.compensation.avg_merit_increase_pct == null ? "No merit cycle in FY24" : "Average merit increase"],
        [`${(s.compensation.gender_pay_ratio_within_job * 100).toFixed(1)}¢`, "Women's pay per dollar of men's, same job"],
      ],
      charts: (s) => {
        const out = [
          { type: "bar", title: "Where pay sits in the range", sub: `Employees by compa-ratio at FY${state.fy % 100} year end`, category: "Compa-ratio",
            labels: s.compa_distribution.map((r) => r.band), fmt: fmt.int,
            datasets: [{ label: "Employees", data: s.compa_distribution.map((r) => r.employees) }] },
          { type: "bar", horizontal: true, title: "Pay versus range midpoint, by job family",
            sub: "Average distance from midpoint. Bars right of zero are paid above it.", category: "Job family",
            labels: s.comp_by_family.map((r) => r.job_family), fmt: (v) => v == null ? "–" : `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}%`,
            barColors: s.comp_by_family.map((r) => (r.avg_compa_ratio >= 1 ? 0 : 1)),
            legendItems: [["Above midpoint", 0], ["Below midpoint", 1]],
            datasets: [{ label: "Versus midpoint", data: s.comp_by_family.map((r) => +((r.avg_compa_ratio - 1) * 100).toFixed(1)) }] },
        ];
        if (s.compression) {
          out.push({ type: "bar", wide: true, short: true, title: "Registered nurse pay: new hires vs experienced staff",
            sub: `Average hourly rate. Experienced nurses earn ${s.compression.experience_premium_pct}% more than nurses hired in the last year.`,
            category: "Group", labels: [`Hired in the last year (${s.compression.new_hires_under_1yr})`, `Five or more years (${s.compression.experienced_5yr_plus})`],
            horizontal: true, fmt: fmt.rate, tick: (v) => `$${v}`,
            datasets: [{ label: "Average hourly rate", data: [s.compression.avg_rate_new, s.compression.avg_rate_experienced] }] });
        }
        return out;
      },
    },
  ];

  // ---------------------------------------------------------------- render
  function renderFilters() {
    const fyBox = $("#fy-filter"), gBox = $("#group-filter");
    const radio = (name, value, label, checked) => {
      const l = document.createElement("label");
      const i = document.createElement("input"); i.type = "radio"; i.name = name; i.value = value; i.checked = checked;
      const s = document.createElement("span"); s.textContent = label;
      l.append(i, s); return l;
    };
    state.data.meta.fiscal_years.forEach((fy) => fyBox.append(radio("fy", fy, `FY${fy % 100}`, fy === state.fy)));
    GROUPS.forEach(([v, l]) => gBox.append(radio("group", v, l, v === state.group)));
    fyBox.addEventListener("change", (e) => { state.fy = +e.target.value; render(); });
    gBox.addEventListener("change", (e) => { state.group = e.target.value; render(); });
  }

  function renderBoard(s, p) {
    const e = s.enterprise;
    const cells = [
      ["On payroll", fmt.int(e.headcount_end), p ? `${e.headcount_end - p.enterprise.headcount_end >= 0 ? "+" : "−"}${fmt.int(Math.abs(e.headcount_end - p.enterprise.headcount_end))} vs FY${(state.fy - 1) % 100}` : "At fiscal year end"],
      ["Hired", fmt.int(e.hires), `FY${state.fy % 100}, October to September`],
      ["Left", fmt.int(e.terminations), `${fmt.int(s.retention.voluntary_turnover_rate_pct / e.turnover_rate_pct * 100)}% by choice`],
      ["Turnover", fmt.pct(e.turnover_rate_pct), p ? delta(e.turnover_rate_pct, p.enterprise.turnover_rate_pct) : "Of average headcount"],
    ];
    const board = $("#board");
    board.replaceChildren(...cells.map(([l, v, d]) => {
      const c = document.createElement("div"); c.className = "cell";
      const a = document.createElement("span"); a.className = "label"; a.textContent = l;
      const b = document.createElement("span"); b.className = "value"; b.textContent = v;
      const x = document.createElement("span"); x.className = "delta"; x.textContent = d;
      c.append(a, b, x); return c;
    }));
  }

  function renderRibbon(ser) {
    const rows = ser.headcount;
    state.charts.push(makeChart($("#ribbon"), {
      type: "line", labels: rows.map((r) => r.month), months: rows.map((r) => r.month), events: true, fmt: fmt.int,
      datasets: [{ label: "Headcount", data: rows.map((r) => r.headcount) }],
    }));
  }

  function renderChapters(s, p, ser) {
    const root = $("#chapters"), rail = $("#rail");
    root.replaceChildren(); rail.replaceChildren();
    CHAPTERS.forEach((ch, i) => {
      const story = s.story[ch.story];
      const sec = document.createElement("section"); sec.className = "chapter"; sec.id = ch.id;
      sec.setAttribute("aria-labelledby", `${ch.id}-h`);
      const head = document.createElement("div"); head.className = "ch-head";
      const n = document.createElement("span"); n.className = "n"; n.textContent = i + 1;
      head.append(n, document.createTextNode(ch.name));
      const h2 = document.createElement("h2"); h2.id = `${ch.id}-h`; h2.textContent = story.headline;
      const body = document.createElement("p"); body.className = "body"; body.textContent = story.body;
      const kpis = document.createElement("div"); kpis.className = "kpis";
      ch.kpis(s, p).forEach(([v, l]) => {
        const k = document.createElement("div"); k.className = "kpi";
        const a = document.createElement("span"); a.className = "v"; a.textContent = v;
        const b = document.createElement("span"); b.className = "l"; b.textContent = l;
        k.append(a, b); kpis.append(k);
      });
      const charts = document.createElement("div"); charts.className = "charts";
      sec.append(head, h2, body, kpis, charts);
      root.append(sec);
      ch.charts(s, ser).forEach((spec) => {
        if (!spec.labels.length) return;
        const { fig, canvas } = figure(spec);
        charts.append(fig);
        state.charts.push(makeChart(canvas, spec));
      });
      const li = document.createElement("li"); const a = document.createElement("a"); a.href = `#${ch.id}`;
      const num = document.createElement("span"); num.className = "n"; num.textContent = i + 1;
      a.append(num, document.createTextNode(ch.name)); li.append(a); rail.append(li);
    });
    observeRail();
  }

  let observer;
  function observeRail() {
    if (observer) observer.disconnect();
    const links = [...document.querySelectorAll("#rail a")];
    observer = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        links.forEach((l) => l.setAttribute("aria-current", String(l.hash === `#${en.target.id}`)));
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    document.querySelectorAll(".chapter").forEach((c) => observer.observe(c));
  }

  function renderQuestions() {
    const qs = ["Why did nursing turnover spike in FY25?", "Which departments carry the most overtime?",
      "Did the market adjustment pay off?", "How much faster are cases routed since AI triage?",
      "Where do we lose people in their first year?", "Which roles take longest to fill?",
      "Is there a gender pay gap within jobs?"];
    $("#questions").replaceChildren(...qs.map((q) => { const li = document.createElement("li"); li.textContent = q; return li; }));
  }

  function render() {
    state.charts.forEach((c) => c.destroy());
    state.charts = [];
    tip.hidden = true;
    const s = state.data.slices[state.fy][state.group];
    const p = state.data.slices[state.fy - 1] ? state.data.slices[state.fy - 1][state.group] : null;
    const ser = state.data.series[state.group];
    renderBoard(s, p);
    renderRibbon(ser);
    renderChapters(s, p, ser);
  }

  // ---------------------------------------------------------------- theme
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("ws-theme"); } catch (_) { /* storage unavailable */ }
    if (saved) document.documentElement.dataset.theme = saved;
    $("#theme-toggle").addEventListener("click", () => {
      const next = isDark() ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("ws-theme", next); } catch (_) { /* ignore */ }
      if (state.data) render();
    });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (state.data) render(); });
  }

  initTheme();
  fetch("data/metrics.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      state.data = data;
      state.fy = data.meta.fiscal_years[data.meta.fiscal_years.length - 1];
      renderFilters(); renderQuestions(); render();
      addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });
    })
    .catch((err) => {
      console.error(err);
      $("#chapters").textContent = state.data
        ? `The page hit an error while drawing charts: ${err.message}`
        : "The data file didn't load. Run `python -m metrics.build`, then serve the app folder (for example, `python -m http.server -d app`).";
    });
})();
