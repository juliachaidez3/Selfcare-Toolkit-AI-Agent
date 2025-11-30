import { useState } from 'react'
import { signInWithEmailAndPassword } from 'firebase/auth'
import { auth } from '../firebase/config'

function Login({ onBack, onSuccess }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!email || !password) {
      setError('Please fill in all fields')
      return
    }

    setLoading(true)

    try {
      await signInWithEmailAndPassword(auth, email, password)
      // Success - user is automatically signed in
      onSuccess()
    } catch (err) {
      console.error('Login error:', err)
      if (err.code === 'auth/user-not-found') {
        setError('No account found with this email. Please sign up.')
      } else if (err.code === 'auth/wrong-password') {
        setError('Incorrect password')
      } else if (err.code === 'auth/invalid-email') {
        setError('Invalid email address')
      } else if (err.code === 'auth/invalid-credential') {
        setError('Invalid email or password')
      } else {
        setError('Failed to log in. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-form-container">
      <h2>Log In</h2>
      <p className="question-subtitle">Welcome back! Please log in to continue</p>
      
      {error && <div className="alert">{error}</div>}

      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={loading}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={loading}
          required
        />
        <div className="button-group">
          <button type="button" className="back-button" onClick={onBack} disabled={loading}>
            Back
          </button>
          <button type="submit" className="next-button" disabled={loading}>
            {loading ? 'Logging In...' : 'Log In'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default Login

