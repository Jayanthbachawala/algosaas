import { useState } from 'react'
import { apiPost } from '../../api/client'

export default function BrokerConnectionsPage({ userId }) {
  const [broker, setBroker] = useState('Zerodha')
  const [url, setUrl] = useState('')

  const connect = async () => {
    const res = await apiPost('/api/v1/broker/oauth/connect', {
      user_id: userId,
      broker_name: broker,
      client_code: `${broker.toLowerCase()}-client`
    })
    setUrl(res.authorization_url)
  }

  return (
    <section className="card">
      <h3>Broker Connections</h3>
      <div className="row">
        <select value={broker} onChange={(e) => setBroker(e.target.value)}>
          <option>Zerodha</option><option>Upstox</option><option>Dhan</option><option>Shoonya</option>
        </select>
        <button onClick={connect}>Connect Broker</button>
      </div>
      {url && <p>OAuth URL: <a href={url}>{url}</a></p>}
    </section>
  )
}
