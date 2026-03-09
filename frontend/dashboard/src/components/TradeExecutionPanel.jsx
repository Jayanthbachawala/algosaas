import { useState } from 'react'
import { apiPost } from '../api/client'

export default function TradeExecutionPanel({ userId }) {
  const [mode, setMode] = useState('LIVE')
  const [form, setForm] = useState({ broker_name: 'Zerodha', symbol: 'NIFTY', strike: 25000, option_type: 'CE', side: 'BUY', quantity: 50, price: 120 })
  const [result, setResult] = useState(null)

  const execute = async () => {
    const payload = { ...form, user_id: userId, entry_price: Number(form.price) }
    const endpoint = mode === 'LIVE' ? '/api/v1/trade/execute/live' : '/api/v1/trade/execute/paper'
    const res = await apiPost(endpoint, payload)
    setResult(res)
  }

  return (
    <section className="card">
      <h3>Trade Execution</h3>
      <div className="row">
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="LIVE">LIVE MODE</option>
          <option value="PAPER">PAPER MODE</option>
        </select>
        <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} />
        <input value={form.strike} onChange={(e) => setForm({ ...form, strike: Number(e.target.value) })} />
        <input value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} />
        <input value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} />
        <button onClick={execute}>Execute</button>
      </div>
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </section>
  )
}
