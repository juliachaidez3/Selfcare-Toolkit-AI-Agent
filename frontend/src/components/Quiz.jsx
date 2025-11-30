import { useState } from 'react'

const TOTAL_QUESTIONS = 5

function Quiz({ quizData, onUpdateQuizData, onGenerateToolkit }) {
  const [currentQuestion, setCurrentQuestion] = useState(1)

  const handleNext = () => {
    if (validateCurrentQuestion()) {
      if (currentQuestion < TOTAL_QUESTIONS) {
        setCurrentQuestion(currentQuestion + 1)
      } else {
        onGenerateToolkit()
      }
    }
  }

  const handlePrev = () => {
    if (currentQuestion > 1) {
      setCurrentQuestion(currentQuestion - 1)
    }
  }

  const validateCurrentQuestion = () => {
    if (currentQuestion === 1) {
      if (!quizData.struggle.trim()) {
        alert('Please answer the question before continuing.')
        return false
      }
    } else if (currentQuestion === 2) {
      if (!quizData.mood.trim()) {
        alert('Please answer the question before continuing.')
        return false
      }
    } else if (currentQuestion === 3) {
      if (!quizData.focus) {
        alert('Please select an option before continuing.')
        return false
      }
    } else if (currentQuestion === 4) {
      if (quizData.copingPreferences.length === 0) {
        alert('Please select at least one option before continuing.')
        return false
      }
    } else if (currentQuestion === 5) {
      if (!quizData.energyLevel) {
        alert('Please select an option before continuing.')
        return false
      }
    }
    return true
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && (currentQuestion === 1 || currentQuestion === 2)) {
      handleNext()
    }
  }

  const progressPercentage = (currentQuestion / TOTAL_QUESTIONS) * 100

  return (
    <div className="quiz-page active">
      {/* Progress Bar */}
      <div className="progress-container">
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${progressPercentage}%` }}
          ></div>
        </div>
        <span className="progress-text">
          Question {currentQuestion} of {TOTAL_QUESTIONS}
        </span>
      </div>

      {/* Question 1: Struggle */}
      {currentQuestion === 1 && (
        <div className="question-page active">
          <h2>What are you struggling with right now?</h2>
          <p className="question-subtitle">
            This helps us understand what you need support with.
          </p>
          <input
            type="text"
            value={quizData.struggle}
            onChange={(e) => onUpdateQuizData('struggle', e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="e.g., stress, anxiety, feeling overwhelmed..."
          />
          <button className="next-button" onClick={handleNext}>
            Next
          </button>
        </div>
      )}

      {/* Question 2: Mood */}
      {currentQuestion === 2 && (
        <div className="question-page active">
          <h2>How are you feeling right now?</h2>
          <p className="question-subtitle">
            Your current mood helps us suggest appropriate activities.
          </p>
          <input
            type="text"
            value={quizData.mood}
            onChange={(e) => onUpdateQuizData('mood', e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="e.g., anxious, sad, frustrated, tired..."
          />
          <div className="button-group">
            <button className="back-button" onClick={handlePrev}>
              Back
            </button>
            <button className="next-button" onClick={handleNext}>
              Next
            </button>
          </div>
        </div>
      )}

      {/* Question 3: Focus */}
      {currentQuestion === 3 && (
        <div className="question-page active">
          <h2>What kind of support are you looking for?</h2>
          <p className="question-subtitle">
            Choose what fits your current needs.
          </p>
          <div className="option-group">
            <label className="option-card">
              <input
                type="radio"
                name="focus"
                value="immediate actions"
                checked={quizData.focus === 'immediate actions'}
                onChange={(e) => onUpdateQuizData('focus', e.target.value)}
              />
              <div className="option-content">
                <strong>Immediate Actions</strong>
                <p>Quick things I can do right now</p>
              </div>
            </label>
            <label className="option-card">
              <input
                type="radio"
                name="focus"
                value="short-term practices"
                checked={quizData.focus === 'short-term practices'}
                onChange={(e) => onUpdateQuizData('focus', e.target.value)}
              />
              <div className="option-content">
                <strong>Short-term Practices</strong>
                <p>Activities for the next few days</p>
              </div>
            </label>
            <label className="option-card">
              <input
                type="radio"
                name="focus"
                value="long-term habits"
                checked={quizData.focus === 'long-term habits'}
                onChange={(e) => onUpdateQuizData('focus', e.target.value)}
              />
              <div className="option-content">
                <strong>Long-term Habits</strong>
                <p>Building lasting wellness routines</p>
              </div>
            </label>
          </div>
          <div className="button-group">
            <button className="back-button" onClick={handlePrev}>
              Back
            </button>
            <button className="next-button" onClick={handleNext}>
              Next
            </button>
          </div>
        </div>
      )}

      {/* Question 4: Coping Preferences */}
      {currentQuestion === 4 && (
		<div>
        <div className="question-page active">
          <h2>What types of activities help you feel better?</h2>
          <p className="question-subtitle">
            Select all that apply - this helps us personalize your toolkit.
          </p>
          <div className="checkbox-group">
            <label className="checkbox-card">
              <input
                type="checkbox"
                value="quiet"
                checked={quizData.copingPreferences.includes('quiet')}
                onChange={(e) => {
                  const newPrefs = e.target.checked
                    ? [...quizData.copingPreferences, 'quiet']
                    : quizData.copingPreferences.filter(p => p !== 'quiet')
                  onUpdateQuizData('copingPreferences', newPrefs)
                }}
              />
              <span className="checkbox-text">Quiet activities</span>
            </label>
            <label className="checkbox-card">
              <input
                type="checkbox"
                value="creative"
                checked={quizData.copingPreferences.includes('creative')}
                onChange={(e) => {
                  const newPrefs = e.target.checked
                    ? [...quizData.copingPreferences, 'creative']
                    : quizData.copingPreferences.filter(p => p !== 'creative')
                  onUpdateQuizData('copingPreferences', newPrefs)
                }}
              />
              <span className="checkbox-text">Creative activities</span>
            </label>
            <label className="checkbox-card">
              <input
                type="checkbox"
                value="active"
                checked={quizData.copingPreferences.includes('active')}
                onChange={(e) => {
                  const newPrefs = e.target.checked
                    ? [...quizData.copingPreferences, 'active']
                    : quizData.copingPreferences.filter(p => p !== 'active')
                  onUpdateQuizData('copingPreferences', newPrefs)
                }}
              />
              <span className="checkbox-text">Active/movement</span>
            </label>
            <label className="checkbox-card">
              <input
                type="checkbox"
                value="social"
                checked={quizData.copingPreferences.includes('social')}
                onChange={(e) => {
                  const newPrefs = e.target.checked
                    ? [...quizData.copingPreferences, 'social']
                    : quizData.copingPreferences.filter(p => p !== 'social')
                  onUpdateQuizData('copingPreferences', newPrefs)
                }}
              />
              <span className="checkbox-text">Social connection</span>
            </label>
            <label className="checkbox-card">
              <input
                type="checkbox"
                value="reflective"
                checked={quizData.copingPreferences.includes('reflective')}
                onChange={(e) => {
                  const newPrefs = e.target.checked
                    ? [...quizData.copingPreferences, 'reflective']
                    : quizData.copingPreferences.filter(p => p !== 'reflective')
                  onUpdateQuizData('copingPreferences', newPrefs)
                }}
              />
              <span className="checkbox-text">Reflective/journaling</span>
            </label>
            <label className="checkbox-card">
              <input
                type="checkbox"
                value="sensory"
                checked={quizData.copingPreferences.includes('sensory')}
                onChange={(e) => {
                  const newPrefs = e.target.checked
                    ? [...quizData.copingPreferences, 'sensory']
                    : quizData.copingPreferences.filter(p => p !== 'sensory')
                  onUpdateQuizData('copingPreferences', newPrefs)
                }}
              />
              <span className="checkbox-text">Sensory experiences</span>
            </label>
          </div>
          </div>
          <div className="button-group">
            <button className="back-button" onClick={handlePrev}>
              Back
            </button>
            <button className="next-button" onClick={handleNext}>
              Next
            </button>
          </div>
        </div>
      )}

      {/* Question 5: Energy Level */}
      {currentQuestion === 5 && (
        <div className="question-page active">
          <h2>How much energy do you have right now?</h2>
          <p className="question-subtitle">
            This helps us suggest activities that match your current capacity.
          </p>
          <div className="option-group">
            <label className="option-card">
              <input
                type="radio"
                name="energy"
                value="low"
                checked={quizData.energyLevel === 'low'}
                onChange={(e) => onUpdateQuizData('energyLevel', e.target.value)}
              />
              <div className="option-content">
                <strong>Low Energy</strong>
                <p>I need gentle, low-effort activities</p>
              </div>
            </label>
            <label className="option-card">
              <input
                type="radio"
                name="energy"
                value="medium"
                checked={quizData.energyLevel === 'medium'}
                onChange={(e) => onUpdateQuizData('energyLevel', e.target.value)}
              />
              <div className="option-content">
                <strong>Medium Energy</strong>
                <p>I can handle moderate activities</p>
              </div>
            </label>
            <label className="option-card">
              <input
                type="radio"
                name="energy"
                value="high"
                checked={quizData.energyLevel === 'high'}
                onChange={(e) => onUpdateQuizData('energyLevel', e.target.value)}
              />
              <div className="option-content">
                <strong>High Energy</strong>
                <p>I'm ready for more active approaches</p>
              </div>
            </label>
          </div>
          <div className="button-group">
            <button className="back-button" onClick={handlePrev}>
              Back
            </button>
            <button className="next-button" onClick={handleNext}>
              Generate My Toolkit
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default Quiz

