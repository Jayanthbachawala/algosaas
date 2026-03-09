import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'

export default function NotificationsPanel({ userId }) {
  const [items, setItems] = useState([])

  useEffect(() => {
    if (!userId) return
    apiGet(`/api/v1/notifications/user/${userId}`)
      .then((r) => setItems(r.notifications || []))
      .catch(() => setItems([]))
  }, [userId])

  return (
    <section className="card">
      <h3>Notifications</h3>
      <ul>
        {items.slice(0, 6).map((n, i) => (
          <li key={i}>{n.notification_type || n.subject}: {n.message || '-'}</li>
        ))}
      </ul>
    </section>
  )
}
