let currentChart = null;

async function showChart() {
  if (!activeFilepath || !activeSlug) return;
  const body = document.getElementById("preview-body");

  // Fetch stats to know which columns are numeric
  let statsData;
  try {
    const resp = await fetch(`/api/file/${activeSlug}/${encodeURIComponent(activeFilepath)}/stats`);
    statsData = await resp.json();
  } catch (e) {
    body.innerHTML = '<div class="empty-state">Failed to load chart data</div>';
    return;
  }

  // Build config UI
  let html = '<div class="chart-config">';
  html += '<span style="font-size:.75rem;color:var(--muted);">X Axis: </span>';
  html += '<select id="chart-x-col">';
  for (const h of statsData.headers) {
    html += `<option value="${escHtml(h)}">${escHtml(h)}</option>`;
  }
  html += '</select>';
  html += '<span style="font-size:.75rem;color:var(--muted);">Y Axis: </span>';
  html += '<select id="chart-y-col">';
  for (const h of statsData.headers) {
    const s = statsData.stats[h] || {};
    if (s.numeric) html += `<option value="${escHtml(h)}">${escHtml(h)}</option>`;
  }
  html += '</select>';
  html += '<span style="font-size:.75rem;color:var(--muted);">Type: </span>';
  html += '<select id="chart-type"><option value="bar">Bar</option><option value="line">Line</option></select>';
  html += '<button class="btn-sm" onclick="renderChart()">Draw</button>';
  html += '</div>';
  html += '<div class="chart-container"><canvas id="chart-canvas"></canvas></div>';
  body.innerHTML = html;
}

function renderChart() {
  const xCol = document.getElementById("chart-x-col")?.value;
  const yCol = document.getElementById("chart-y-col")?.value;
  const chartType = document.getElementById("chart-type")?.value || "bar";
  if (!xCol || !yCol || !activeCsvData) return;

  const headers = activeCsvData.headers;
  const xIdx = headers.indexOf(xCol);
  const yIdx = headers.indexOf(yCol);
  if (xIdx < 0 || yIdx < 0) return;

  const labels = [];
  const values = [];
  for (let i = 0; i < Math.min(activeCsvData.rows.length, 200); i++) {
    const row = activeCsvData.rows[i];
    labels.push(row[xIdx] || "");
    const num = parseFloat(row[yIdx]);
    if (!isNaN(num)) values.push(num);
  }

  if (currentChart) currentChart.destroy();

  const ctx = document.getElementById("chart-canvas").getContext("2d");
  currentChart = new Chart(ctx, {
    type: chartType,
    data: {
      labels: labels.slice(0, values.length),
      datasets: [{
        label: yCol,
        data: values,
        backgroundColor: chartType === "bar"
          ? values.map(() => "rgba(88,166,255,0.5)")
          : "rgba(88,166,255,0.2)",
        borderColor: "rgba(88,166,255,1)",
        borderWidth: 1,
        tension: 0.2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#c9d1d9" } }
      },
      scales: {
        x: {
          ticks: { color: "#8b949e", maxRotation: 45 },
          grid: { color: "rgba(42,45,58,0.3)" }
        },
        y: {
          ticks: { color: "#8b949e" },
          grid: { color: "rgba(42,45,58,0.3)" },
          beginAtZero: true
        }
      }
    }
  });
}

function escHtml(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
