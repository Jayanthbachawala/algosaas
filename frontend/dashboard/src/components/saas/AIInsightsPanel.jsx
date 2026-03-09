export default function AIInsightsPanel({ insights }) {
  const p = insights?.prediction || {}
  return (
    <section className="card">
      <h3>AI Insights</h3>
      <div className="grid2">
        <div>Probability: {p.probability ?? '-'}</div>
        <div>Market Regime: {p.market_regime ?? '-'}</div>
        <div>Strategy: {p.strategy ?? '-'}</div>
        <div>Expected Move: {p.expected_move ?? '-'}</div>
      </div>
    </section>
  )
}
