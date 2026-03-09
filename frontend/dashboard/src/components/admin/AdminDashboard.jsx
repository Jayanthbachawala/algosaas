import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../../api/client'

export default function AdminDashboard() {
  const [stats, setStats] = useState({})
  const [monitor, setMonitor] = useState({})

  const load = () => {
    apiGet('/api/v1/admin/dashboard').then(setStats).catch(() => setStats({}))
    apiGet('/api/v1/admin/monitoring').then(setMonitor).catch(() => setMonitor({}))
  }

  useEffect(() => { load() }, [])

  return (
    <section className="card">
      <h3>Master Admin Dashboard</h3>
      <div className="grid2">
        <div>Active Users: {stats.active_users ?? '-'}</div>
        <div>Signals Today: {stats.signals_generated_today ?? '-'}</div>
        <div>Trades Today: {stats.trades_executed_today ?? '-'}</div>
        <div>Revenue: {stats.total_revenue_paise ?? '-'}</div>
      </div>
      <div className="row" style={{marginTop:8}}>
        <button onClick={() => apiPost('/api/v1/admin/disable-trading', {}).then(load)}>Disable Trading</button>
        <button onClick={() => apiPost('/api/v1/admin/enable-trading', {}).then(load)}>Enable Trading</button>
      </div>
      <p>Redis Memory: {monitor.redis_memory_used ?? '-'}</p>
      <p>Active Sessions: {monitor.active_sessions ?? '-'}</p>
    </section>
  )
}
