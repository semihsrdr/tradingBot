document.addEventListener('DOMContentLoaded', function() {

    const portfolioSummaryEl = document.getElementById('portfolio-summary');
    const openPositionsContainerEl = document.getElementById('open-positions-container');
    const tradeLogEl = document.getElementById('trade-log');
    const lastUpdatedEl = document.getElementById('last-updated');
    const equityChartEl = document.getElementById('equity-chart');
    let equityChart;

    // --- Chart.js Initialization ---
    function createEquityChart() {
        if (!equityChartEl) return;
        // Destroy existing chart if it exists
        if (equityChart) {
            equityChart.destroy();
        }
        const ctx = equityChartEl.getContext('2d');
        equityChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Total Equity (USD)',
                    data: [],
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true,
                    tension: 0.1,
                    pointRadius: 2, // Make points visible
                    borderWidth: 2 // Make line thicker
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        ticks: {
                            maxTicksLimit: 10 // Limit number of x-axis labels
                        },
                        title: {
                            display: true,
                            text: 'Time'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Equity ($)'
                        }
                    }
                }
            }
        });
    }

    async function fetchData() {
        try {
            // Fetch all data in parallel
            const [summaryRes, positionsRes, logRes, historyRes] = await Promise.all([
                fetch('/api/portfolio_summary'),
                fetch('/api/open_positions'),
                fetch('/api/trade_log'),
                fetch('/api/portfolio_history')
            ]);

            const summary = await summaryRes.json();
            updatePortfolioSummary(summary);

            const positions = await positionsRes.json();
            updateOpenPositions(positions);

            const log = await logRes.json();
            updateTradeLog(log.log_content);
            
            const history = await historyRes.json();
            updateEquityChart(history);

            lastUpdatedEl.textContent = `Last Updated: ${new Date().toLocaleTimeString()}`;

        } catch (error) {
            console.error("Error fetching data:", error);
            const botStatusEl = document.getElementById('bot-status');
            botStatusEl.textContent = 'Error';
            botStatusEl.classList.remove('bg-success');
            botStatusEl.classList.add('bg-danger');
        }
    }

    function updatePortfolioSummary(summary) {
        const pnlClass = summary.unrealized_pnl_usd >= 0 ? 'pnl-positive' : 'pnl-negative';
        portfolioSummaryEl.innerHTML = `
            <div class="col">
                <h5>Available Balance</h5>
                <p class="fs-4">$${summary.available_balance_usd.toFixed(2)}</p>
            </div>
            <div class="col">
                <h5>Total Equity</h5>
                <p class="fs-4">$${summary.total_equity_usd.toFixed(2)}</p>
            </div>
            <div class="col">
                <h5>Unrealized PnL</h5>
                <p class="fs-4 ${pnlClass}">$${summary.unrealized_pnl_usd.toFixed(2)}</p>
            </div>
            <div class="col">
                <h5>Open Positions</h5>
                <p class="fs-4">${summary.open_positions_count}</p>
            </div>
        `;
    }

    function updateOpenPositions(positions) {
        if (Object.keys(positions).length === 0) {
            openPositionsContainerEl.innerHTML = '<p class="text-center">No open positions.</p>';
            return;
        }

        let html = '';
        for (const symbol in positions) {
            const pos = positions[symbol];
            const pnl = pos.unrealized_pnl || 0;
            const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            const margin = pos.margin || 0;
            const pnlPct = margin > 0 ? (pnl / margin) * 100 : 0;

            html += `
                <div class="position-card">
                    <div class="d-flex justify-content-between">
                        <h5 class="position-header">${symbol} (${pos.side.toUpperCase()})</h5>
                        <span class="badge bg-${pos.side === 'long' ? 'success' : 'danger'}">${pos.leverage}x</span>
                    </div>
                    <div class="row mt-2">
                        <div class="col"><strong>Qty:</strong> ${pos.quantity.toFixed(5)}</div>
                        <div class="col"><strong>Entry:</strong> $${pos.entry_price.toFixed(2)}</div>
                        <div class="col"><strong>Current:</strong> $${pos.current_price.toFixed(2)}</div>
                    </div>
                    <div class="row mt-2">
                        <div class="col"><strong>Margin:</strong> $${margin.toFixed(2)}</div>
                        <div class="col"><strong>PnL:</strong> <span class="${pnlClass}">$${pnl.toFixed(2)} (${pnlPct.toFixed(2)}%)</span></div>
                    </div>
                </div>
            `;
        }
        openPositionsContainerEl.innerHTML = html;
    }

    function updateTradeLog(logContent) {
        tradeLogEl.textContent = logContent;
        tradeLogEl.scrollTop = tradeLogEl.scrollHeight; // Auto-scroll to bottom
    }

    function updateEquityChart(history) {
        if (!equityChart || !history) return;

        const labels = history.map(point => new Date(point.timestamp).toLocaleTimeString());
        const data = history.map(point => point.equity);

        equityChart.data.labels = labels;
        equityChart.data.datasets[0].data = data;
        equityChart.update();
    }

    // --- Initial Load ---
    createEquityChart();
    fetchData();
    setInterval(fetchData, 5000); // Refresh every 5 seconds
});
