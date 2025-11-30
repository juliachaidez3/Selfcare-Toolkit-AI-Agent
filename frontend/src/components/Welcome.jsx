function Welcome({ onStartQuiz }) {
  return (
    <div className="quiz-page active welcome-page">
      <h1>Self-Care Toolkit</h1>
      <p className="welcome-text">
        Get personalized self-care recommendations tailored just for you. Answer a few quick questions and we'll create your custom wellness toolkit.
      </p>
      <button className="primary-button" onClick={onStartQuiz}>
        Get Started
      </button>
    </div>
  )
}

export default Welcome

