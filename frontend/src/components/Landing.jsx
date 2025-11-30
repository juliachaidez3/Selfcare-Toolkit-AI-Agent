function Landing({ onSignUp, onLogin }) {
  return (
    <div className="quiz-page active landing-page">
      <h1>Self-Care Toolkit</h1>
      <p className="welcome-text">
        Get personalized self-care recommendations tailored just for you. Sign up or log in to get started.
      </p>
      <div className="auth-buttons">
        <button className="primary-button signup-button" onClick={onSignUp}>
          Sign Up
        </button>
        <button className="primary-button login-button" onClick={onLogin}>
          Log In
        </button>
      </div>
    </div>
  )
}

export default Landing

