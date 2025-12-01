function Navbar({ user, currentView, onLogout, onBackToDashboard, onLogin, onExitQuiz, showToolkit, authView }) {
  // If user is in quiz, show only exit button
  if (currentView === 'quiz') {
    return (
      <nav className="navbar">
        <div className="navbar-content">
          <div className="navbar-left"></div>
          <div className="navbar-right">
            <button className="navbar-exit-button" onClick={onExitQuiz}>
              ✕ Exit
            </button>
          </div>
        </div>
      </nav>
    )
  }

  // If user is logged in
  if (user) {
    // Show back button if viewing toolkit or if not on dashboard
    const showBackButton = showToolkit || currentView === 'toolkit' || (currentView !== 'dashboard' && currentView !== 'quiz')
    
    return (
      <nav className="navbar">
        <div className="navbar-content">
          <div className="navbar-left">
            {showBackButton && (
              <button className="navbar-back-button" onClick={onBackToDashboard}>
                ← Back to Dashboard
              </button>
            )}
          </div>
          <div className="navbar-right">
            <button className="navbar-logout-button" onClick={onLogout}>
              Log Out
            </button>
          </div>
        </div>
      </nav>
    )
  }

  // If user is not logged in
  // Don't show Log In button if already on login or signup page
  if (authView === 'login' || authView === 'signup') {
    return (
      <nav className="navbar">
        <div className="navbar-content">
          <div className="navbar-left"></div>
          <div className="navbar-right"></div>
        </div>
      </nav>
    )
  }
  
  return (
    <nav className="navbar">
      <div className="navbar-content">
        <div className="navbar-left"></div>
        <div className="navbar-right">
          <button className="navbar-login-button" onClick={onLogin}>
            Log In
          </button>
        </div>
      </div>
    </nav>
  )
}

export default Navbar

