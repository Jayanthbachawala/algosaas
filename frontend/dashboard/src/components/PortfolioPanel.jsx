export default function PortfolioPanel({ portfolio, exposure }) {
  return (
    <section className="card">
      <h3>Portfolio</h3>
      <div className="grid2">
        <div>Net PnL: {portfolio?.net_pnl ?? '-'}</div>
        <div>Unrealized: {portfolio?.unrealized_pnl ?? '-'}</div>
        <div>Realized: {portfolio?.realized_pnl ?? '-'}</div>
        <div>Gross Exposure: {exposure?.gross_exposure ?? '-'}</div>
      </div>
    </section>
  )
}
