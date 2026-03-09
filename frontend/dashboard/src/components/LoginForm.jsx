import { useState } from 'react'
import { apiPost } from '../api/client'

export default function LoginForm({ onLogin }) {
  const [email, setEmail] = useState('trader@algosaas.in')
  const [passwordHash, setPasswordHash] = useState('demo_hash')
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const res = await apiPost('/api/v1/auth/login', {
        email,
        password_hash: passwordHash,
      })
      onLogin(res)
    } catch (err) {
      setError(String(err))
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Sign in</h2>
      <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
      <input value={passwordHash} onChange={(e) => setPasswordHash(e.target.value)} placeholder="Password Hash" />
      <button type="submit">Login</button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
