import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import LoginForm from '../components/LoginForm'
import SignalPanel from '../components/SignalPanel'
import PortfolioPanel from '../components/PortfolioPanel'
import TradeExecutionPanel from '../components/TradeExecutionPanel'
import DashboardLayout from '../layouts/DashboardLayout'
import { useMarketStream } from '../hooks/useMarketStream'

export default function App() {
  const [session, setSession] = useState(null)
  const [dashboard, setDashboard] = useState(null)
  const stream = useMarketStream('NIFTY')

  useEffect(() => {
    if (!session?.user_id) return
    apiGet(`/api/v1/dashboard/${session.user_id}`).then(setDashboard).catch(console.error)
  }, [session])

  if (!session) {
    return (
      <div className="center">
        <LoginForm onLogin={setSession} />
      </div>
    )
  }

  const signals = dashboard?.signals?.signals ?? stream?.signals ?? []

  return (
    <DashboardLayout user={session}>
      <section className="card">
        <h3>WebSocket Market Stream</h3>
        <pre>{JSON.stringify(stream?.tick, null, 2)}</pre>
      </section>
      <SignalPanel signals={signals} />
      <PortfolioPanel portfolio={dashboard?.portfolio} exposure={dashboard?.exposure} />
      <TradeExecutionPanel userId={session.user_id} />
    </DashboardLayout>
  )
}
