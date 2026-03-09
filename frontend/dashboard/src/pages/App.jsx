import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import LoginForm from '../components/LoginForm'
import SignalPanel from '../components/SignalPanel'
import PortfolioPanel from '../components/PortfolioPanel'
import TradeExecutionPanel from '../components/TradeExecutionPanel'
import DashboardLayout from '../layouts/DashboardLayout'
import { useMarketStream } from '../hooks/useMarketStream'
import AIInsightsPanel from '../components/saas/AIInsightsPanel'
import NotificationsPanel from '../components/saas/NotificationsPanel'
import BrokerConnectionsPage from '../components/saas/BrokerConnectionsPage'
import SubscriptionManagementPage from '../components/saas/SubscriptionManagementPage'
import AdminDashboard from '../components/admin/AdminDashboard'

export default function App() {
  const [session, setSession] = useState(null)
  const [dashboard, setDashboard] = useState(null)
  const [brain, setBrain] = useState(null)
  const stream = useMarketStream('NIFTY')

  useEffect(() => {
    if (!session?.user_id) return
    apiGet(`/api/v1/dashboard/${session.user_id}`).then(setDashboard).catch(console.error)
    apiGet('/api/v1/brain/NIFTY').then(setBrain).catch(() => setBrain(null))
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
      <AIInsightsPanel insights={{ prediction: signals?.[0] || {}, brain }} />
      <PortfolioPanel portfolio={dashboard?.portfolio} exposure={dashboard?.exposure} />
      <TradeExecutionPanel userId={session.user_id} />
      <BrokerConnectionsPage userId={session.user_id} />
      <SubscriptionManagementPage userId={session.user_id} />
      <NotificationsPanel userId={session.user_id} />
      <AdminDashboard />
    </DashboardLayout>
  )
}
