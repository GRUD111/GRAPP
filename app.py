import streamlit as st
import json
import datetime
from collections import deque

# Konfigurimi
MAX_RECORDS = 2000
OI_SPIKE_THRESHOLD = 0.50

def format_large_number(num):
    """Formaton numrat në K, M, B"""
    if num == 0:
        return "0"
    if num < 1000:
        return f"{num:,.0f}"
    elif num < 1_000_000:
        return f"{num/1000:.1f}K"
    elif num < 1_000_000_000:
        return f"{num/1_000_000:.1f}M"
    else:
        return f"{num/1_000_000_000:.2f}B"

def generate_html(symbols):
    symbols_list = json.dumps(symbols)
    html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>OI Futures Monitor</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 15px;
                background-color: #f4f4f4;
            }}
            h2, h3 {{ margin: 15px 0 10px 0; }}
            table {{
                border-collapse: collapse;
                width: 100%;
                background: white;
            }}
            th, td {{
                padding: 8px;
                text-align: center;
                border: 1px solid #ccc;
                font-size: 13px;
            }}
            th {{
                background-color: #2c3e50;
                color: white;
                position: sticky;
                top: 0;
                z-index: 2;
            }}
            .green {{ color: #27ae60; font-weight: bold; }}
            .red {{ color: #e74c3c; font-weight: bold; }}
            .coins-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 12px;
            }}
            .coin-box {{
                background: white;
                border-radius: 8px;
                padding: 10px;
                border: 1px solid #dcdcdc;
            }}
            .coin-title {{
                text-align: center;
                font-weight: bold;
                font-size: 16px;
                margin-bottom: 6px;
            }}
            .orderbook {{
                font-size: 12.5px;
                margin: 8px 0;
                line-height: 1.4;
            }}
            .coin-table-wrapper {{
                max-height: 320px;
                overflow-y: auto;
            }}
            .ratio {{ font-weight: bold; }}
            .pressure {{
                margin-top: 10px;
                padding: 8px;
                background: #f8f9fa;
                border-radius: 6px;
                font-size: 12px;
            }}
            .pressure-line {{ margin: 2px 0; }}
        </style>
    </head>
    <body>
        <h2>🔴 OI Futures Live Monitor + Counters</h2>
        <h3>📊 Tabelat Individuale Live + Order Book + Significant Pressure</h3>
        <div id="coins-container" class="coins-grid"></div>
        <script>
            let symbols = {symbols_list};
            let oiHistory = {{}};
            let lastOI = {{}};
            let coinTablesHistory = {{}};
            let orderBookData = {{}};
            let levelCounters = {{}};
            let levelMinMax = {{}};

            const BUCKETS = {{
                b1: {{min: 1.01, max: 2.49, label: "1%"}},
                b2: {{min: 2.50, max: 4.00, label: "2.5%"}},
                b3: {{min: 4.01, max: Infinity, label: "4%"}}
            }};

            function getBucket(ratio) {{
                if (ratio < 1.01) return null;
                for (let key in BUCKETS) {{
                    const b = BUCKETS[key];
                    if (ratio >= b.min && (b.max === Infinity || ratio <= b.max)) return key;
                }}
                return "b3";
            }}

            function initLevelData(symbol) {{
                if (!levelCounters[symbol]) levelCounters[symbol] = {{}};
                if (!levelMinMax[symbol]) levelMinMax[symbol] = {{}};
                [200,400,600,800,1000].forEach(lvl => {{
                    if (!levelCounters[symbol][lvl]) {{
                        levelCounters[symbol][lvl] = {{ b1: {{bid:0,ask:0}}, b2: {{bid:0,ask:0}}, b3: {{bid:0,ask:0}} }};
                    }}
                    if (!levelMinMax[symbol][lvl]) {{
                        levelMinMax[symbol][lvl] = {{ bid: {{min: Infinity, max: 0}}, ask: {{min: Infinity, max: 0}} }};
                    }}
                }});
            }}

            function updateMinMax(symbol, lvl, bid, ask) {{
                const mm = levelMinMax[symbol][lvl];
                if (bid > 0) {{ mm.bid.min = Math.min(mm.bid.min, bid); mm.bid.max = Math.max(mm.bid.max, bid); }}
                if (ask > 0) {{ mm.ask.min = Math.min(mm.ask.min, ask); mm.ask.max = Math.max(mm.ask.max, ask); }}
            }}

            function formatNum(n) {{
                if (n === 0 || n === Infinity) return "0";
                if (n < 1000) return n.toLocaleString('de-DE');
                if (n < 1e6) return (n/1000).toFixed(1) + "K";
                if (n < 1e9) return (n/1e6).toFixed(1) + "M";
                return (n/1e9).toFixed(2) + "B";
            }}

            function getRatioDisplay(bid, ask) {{
                if (bid === 0 || ask === 0) {{
                    return {{value: "0.00", color: "gray", circle: "⚪", ratio: 0}};
                }}
                if (bid >= ask) {{
                    const ratio = bid / ask;
                    return {{ value: "+" + ratio.toFixed(2), color: "#e74c3c", circle: "🔴", ratio: ratio }};
                }} else {{
                    const ratio = ask / bid;
                    return {{ value: "-" + ratio.toFixed(2), color: "#27ae60", circle: "🟢", ratio: ratio }};
                }}
            }}

            async function fetchOI(symbol) {{
                try {{
                    const res = await fetch(`https://fapi.binance.com/fapi/v1/openInterest?symbol=${{symbol}}`);
                    const data = await res.json();
                    return parseFloat(data.openInterest);
                }} catch(e) {{ return null; }}
            }}

            async function fetchOrderBook(symbol) {{
                try {{
                    const res = await fetch(`https://fapi.binance.com/fapi/v1/depth?symbol=${{symbol}}&limit=1000`);
                    const data = await res.json();
                    const bids = data.bids || [];
                    const asks = data.asks || [];
                    const levels = [200, 400, 600, 800, 1000];
                    const result = {{ levels: {{}}, significantAsks: [], significantBids: [] }};

                    let bidSum = 0, askSum = 0;
                    let bidTotalValue = 0, askTotalValue = 0;

                    // Llogarit totalin e 1000 niveleve
                    for (let i = 0; i < Math.min(1000, Math.max(bids.length, asks.length)); i++) {{
                        if (i < bids.length) {{
                            const p = parseFloat(bids[i][0]);
                            const q = parseFloat(bids[i][1]);
                            bidTotalValue += p * q;
                        }}
                        if (i < asks.length) {{
                            const p = parseFloat(asks[i][0]);
                            const q = parseFloat(asks[i][1]);
                            askTotalValue += p * q;
                        }}
                    }}

                    // Llogarit cumulative dhe significant levels
                    for (let i = 0; i < Math.min(1000, Math.max(bids.length, asks.length)); i++) {{
                        const bidPrice = i < bids.length ? parseFloat(bids[i][0]) : 0;
                        const bidQty = i < bids.length ? parseFloat(bids[i][1]) : 0;
                        const askPrice = i < asks.length ? parseFloat(asks[i][0]) : 0;
                        const askQty = i < asks.length ? parseFloat(asks[i][1]) : 0;

                        const bidValue = bidPrice * bidQty;
                        const askValue = askPrice * askQty;

                        bidSum += bidValue;
                        askSum += askValue;

                        if (levels.includes(i + 1)) {{
                            const ratioInfo = getRatioDisplay(bidSum, askSum);
                            result.levels[i + 1] = {{
                                bid: bidSum,
                                ask: askSum,
                                ratio: ratioInfo.value,
                                color: ratioInfo.color,
                                circle: ratioInfo.circle,
                                rawRatio: ratioInfo.ratio
                            }};
                        }}

                        // Vetëm nivelet individuale > 1% e totalit
                        if (askTotalValue > 0 && askValue / askTotalValue > 0.01) {{
                            result.significantAsks.push({{
                                level: i + 1,
                                percent: (askValue / askTotalValue * 100).toFixed(2),
                                price: askPrice
                            }});
                        }}
                        if (bidTotalValue > 0 && bidValue / bidTotalValue > 0.01) {{
                            result.significantBids.push({{
                                level: i + 1,
                                percent: (bidValue / bidTotalValue * 100).toFixed(2),
                                price: bidPrice
                            }});
                        }}
                    }}

                    // Rendit nga niveli më i vogël tek më i madhi
                    result.significantAsks.sort((a, b) => a.level - b.level);
                    result.significantBids.sort((a, b) => a.level - b.level);

                    return result;
                }} catch(e) {{
                    return {{ levels: {{}}, significantAsks: [], significantBids: [] }};
                }}
            }}

            function renderCoinTables() {{
                let scrollPositions = {{}};
                document.querySelectorAll(".coin-table-wrapper").forEach(wrapper => {{
                    scrollPositions[wrapper.dataset.symbol] = wrapper.scrollTop;
                }});

                let containerHTML = "";
                for (let symbol of symbols) {{
                    if (!coinTablesHistory[symbol]) coinTablesHistory[symbol] = [];
                    const ob = orderBookData[symbol] || {{ levels: {{}}, significantAsks: [], significantBids: [] }};

                    let rowsHTML = "";
                    coinTablesHistory[symbol].forEach(row => {{
                        const color = parseFloat(row.change) >= 0 ? "green" : "red";
                        rowsHTML += `
                            <tr>
                                <td>${{row.time}}</td>
                                <td class="${{color}}">${{row.change >= 0 ? '+' : ''}}${{row.change}}%</td>
                            </tr>
                        `;
                    }});

                    let obHTML = `<div class="orderbook">`;
                    const levelKeys = [200,400,600,800,1000];
                    levelKeys.forEach(lvl => {{
                        const d = ob.levels[lvl] || {{bid:0, ask:0, ratio:"0.00", color:"gray", circle:"⚪", rawRatio:0}};
                        const counters = levelCounters[symbol]?.[lvl] || {{b1:{{bid:0,ask:0}}, b2:{{bid:0,ask:0}}, b3:{{bid:0,ask:0}}}};
                        const minmax = levelMinMax[symbol]?.[lvl] || {{bid:{{min:0,max:0}}, ask:{{min:0,max:0}}}};
                        let counterHTML = "";
                        Object.keys(BUCKETS).forEach(key => {{
                            const b = BUCKETS[key];
                            const c = counters[key];
                            counterHTML += ` ${{b.label}} ${{c.bid}}-${{c.ask}} |`;
                        }});
                        const bidMinMaxStr = minmax.bid.max > 0 ? `${{formatNum(minmax.bid.min)}}-${{formatNum(minmax.bid.max)}}` : "—";
                        const askMinMaxStr = minmax.ask.max > 0 ? `${{formatNum(minmax.ask.min)}}-${{formatNum(minmax.ask.max)}}` : "—";
                        obHTML += `
                            <strong>${{lvl}} lvl:</strong>
                            B ${{formatNum(d.bid)}} | A ${{formatNum(d.ask)}}
                            <span class="ratio" style="color:${{d.color}}">${{d.circle}} ${{d.ratio}}</span>
                            <span style="font-size:12px; color:#555;">${{counterHTML}}</span><br>
                            <span style="font-size:11.5px; color:#777;">- B ${{bidMinMaxStr}} | A ${{askMinMaxStr}}</span><br>
                        `;
                    }});
                    obHTML += `</div>`;

                    // Significant Pressure
                    let pressureHTML = `<div class="pressure"><strong>Significant Pressure (>1% e totalit - nga niveli më i vogël):</strong><br>`;
                    if (ob.significantAsks && ob.significantAsks.length > 0) {{
                        pressureHTML += `<span style="color:#e74c3c">ASK:</span><br>`;
                        ob.significantAsks.forEach(item => {{
                            pressureHTML += `<div class="pressure-line">LV ${{item.level}} - ${{item.percent}}% @ ${{parseFloat(item.price).toFixed(4)}}$</div>`;
                        }});
                    }}
                    if (ob.significantBids && ob.significantBids.length > 0) {{
                        pressureHTML += `<span style="color:#27ae60">BID:</span><br>`;
                        ob.significantBids.forEach(item => {{
                            pressureHTML += `<div class="pressure-line">LV ${{item.level}} - ${{item.percent}}% @ ${{parseFloat(item.price).toFixed(4)}}$</div>`;
                        }});
                    }}
                    if ((!ob.significantAsks || ob.significantAsks.length === 0) && (!ob.significantBids || ob.significantBids.length === 0)) {{
                        pressureHTML += `<span style="color:#777">No levels >1%</span>`;
                    }}
                    pressureHTML += `</div>`;

                    containerHTML += `
                        <div class="coin-box">
                            <div class="coin-title">${{symbol.replace('USDT', '')}}</div>
                            ${{obHTML}}
                            ${{pressureHTML}}
                            <div class="coin-table-wrapper" data-symbol="${{symbol}}">
                                <table class="coin-table">
                                    <thead>
                                        <tr>
                                            <th>Ora</th>
                                            <th>${{symbol.replace('USDT', '')}} %</th>
                                        </tr>
                                    </thead>
                                    <tbody>${{rowsHTML}}</tbody>
                                </table>
                            </div>
                        </div>
                    `;
                }}
                document.getElementById("coins-container").innerHTML = containerHTML;
                document.querySelectorAll(".coin-table-wrapper").forEach(wrapper => {{
                    const symbol = wrapper.dataset.symbol;
                    if (scrollPositions[symbol] !== undefined) {{
                        wrapper.scrollTop = scrollPositions[symbol];
                    }}
                }});
            }}

            async function updateAll() {{
                const now = Date.now();
                for (let symbol of symbols) {{
                    const currentOI = await fetchOI(symbol);
                    const ob = await fetchOrderBook(symbol);
                    if (currentOI === null) continue;
                    orderBookData[symbol] = ob;
                    initLevelData(symbol);

                    const levelKeys = [200,400,600,800,1000];
                    levelKeys.forEach(lvl => {{
                        const data = ob.levels[lvl];
                        if (!data) return;
                        updateMinMax(symbol, lvl, data.bid, data.ask);
                        const bucketKey = getBucket(data.rawRatio);
                        if (bucketKey) {{
                            if (data.circle === "🔴") levelCounters[symbol][lvl][bucketKey].bid++;
                            else if (data.circle === "🟢") levelCounters[symbol][lvl][bucketKey].ask++;
                        }}
                    }});

                    if (!oiHistory[symbol]) oiHistory[symbol] = [];
                    oiHistory[symbol].unshift({{ oi: currentOI, timestamp: now }});
                    if (oiHistory[symbol].length > 1500) oiHistory[symbol].pop();

                    if (lastOI[symbol]) {{
                        const change = ((currentOI - lastOI[symbol]) / lastOI[symbol]) * 100;
                        if (Math.abs(change) >= {OI_SPIKE_THRESHOLD}) {{
                            const timeStr = new Date(now + 7200000).toISOString().slice(11,19);
                            if (!coinTablesHistory[symbol]) coinTablesHistory[symbol] = [];
                            coinTablesHistory[symbol].unshift({{ time: timeStr, change: change.toFixed(2) }});
                            if (coinTablesHistory[symbol].length > {MAX_RECORDS}) coinTablesHistory[symbol].pop();
                        }}
                    }}
                    lastOI[symbol] = currentOI;
                }}
                renderCoinTables();
            }}

            async function refreshTopSymbols() {{
                const newSymbols = await getTopRangeSymbols();
                if (newSymbols && newSymbols.length > 0) {{
                    symbols = newSymbols;
                    for (let s of symbols) {{
                        if (!oiHistory[s]) oiHistory[s] = [];
                        if (!coinTablesHistory[s]) coinTablesHistory[s] = [];
                        if (!orderBookData[s]) orderBookData[s] = {{ levels: {{}} }};
                    }}
                }}
            }}

            async function getTopRangeSymbols() {{
                try {{
                    const res = await fetch("https://fapi.binance.com/fapi/v1/ticker/24hr");
                    const data = await res.json();
                    let filtered = data.filter(item =>
                        item.symbol.endsWith("USDT") && !item.symbol.includes("_") &&
                        parseFloat(item.highPrice) > 0 && parseFloat(item.lowPrice) > 0
                    );
                    filtered.forEach(item => {{
                        const high = parseFloat(item.highPrice);
                        const low = parseFloat(item.lowPrice);
                        item.rangePercent = ((high - low) / low) * 100;
                    }});
                    filtered.sort((a, b) => b.rangePercent - a.rangePercent);
                    return filtered.slice(0, 2).map(item => item.symbol);
                }} catch (e) {{
                    return symbols;
                }}
            }}

            refreshTopSymbols();
            setInterval(refreshTopSymbols, 60 * 60 * 1000);
            setInterval(updateAll, 4000);
            updateAll();
        </script>
    </body>
    </html>
    """
    return html

def main():
    st.set_page_config(page_title="OI Futures + GB-RY", layout="wide")
    st.title("🔴 OI Futures Monitor + GB-RY Live + Counters")
  
    default = "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT"
    symbols_input = st.text_input("Monedhat (presje):", value=default)
    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
   
    if st.button("NIS MONITORIN LIVE"):
        if symbols:
            html_content = generate_html(symbols)
            st.components.v1.html(html_content, height=1400, scrolling=True)
        else:
            st.error("Vendos të paktën një monedhë!")

if __name__ == "__main__":
    main()
