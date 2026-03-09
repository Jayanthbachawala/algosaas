import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../../api/client'

export default function SubscriptionManagementPage({ userId }) {
  const [plans, setPlans] = useState([])
  const [selected, setSelected] = useState('Basic')

  useEffect(() => {
    apiGet('/api/v1/plans').then((r) => setPlans(r.plans || [])).catch(() => setPlans([]))
  }, [])

  const subscribe = async () => {
    await apiPost('/api/v1/subscribe', { user_id: userId, plan_name: selected, duration_days: 30 })
    alert('Subscription updated')
  }

  return (
    <section className="card">
      <h3>Subscription Management</h3>
      <div className="row">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {plans.map((p) => <option key={p.id || p.name} value={p.name}>{p.name} - ₹{p.price}</option>)}
        </select>
        <button onClick={subscribe}>Subscribe</button>
      </div>
    </section>
  )
}
