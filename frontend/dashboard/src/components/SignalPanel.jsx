export default function SignalPanel({ signals = [] }) {
  return (
    <section className="card">
      <h3>Signal Panel</h3>
      <table>
        <thead>
          <tr>
            <th>Symbol</th><th>Strike</th><th>Type</th><th>Entry</th><th>SL</th><th>Target</th><th>AI Prob</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => (
            <tr key={i}>
              <td>{s.symbol}</td>
              <td>{s.strike}</td>
              <td>{s.option_type}</td>
              <td>{s.entry_price}</td>
              <td>{s.stop_loss}</td>
              <td>{s.target}</td>
              <td>{s.ai_probability_score ?? s.probability_score}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
