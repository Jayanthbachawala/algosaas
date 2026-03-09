export default function DashboardLayout({ children, user }) {
  return (
    <main className="layout">
      <header className="header card">
        <h1>AlgoSaaS Trading Dashboard</h1>
        <div>User: {user?.email || user?.user_id}</div>
      </header>
      {children}
    </main>
  )
}
