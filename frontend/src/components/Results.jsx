import { useState } from 'react'

function Results({ results, error, onRestartQuiz, onBackToHome, onSaveToToolkit, user }) {
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [savedItems, setSavedItems] = useState(new Set())

  const handleSave = async (item, index) => {
    if (!user) {
      alert('Please log in to save items to your toolkit')
      return
    }
    
    try {
      await onSaveToToolkit(item)
      setSavedItems(prev => new Set([...prev, index]))
    } catch (error) {
      console.error('Error saving to toolkit:', error)
      alert('Failed to save to toolkit. Please try again.')
    }
  }

  return (
    <div className="results">
      {error && (
        <div className="alert">
          {error.includes('Safety first') ? `Safety first: ${error}` : `Error: ${error}`}
        </div>
      )}

      {results && results.length > 0 && (
        <>
          <h2>Your Personalized Self-Care Toolkit:</h2>
          <div className="results-container">
            {results.map((item, index) => (
              <div 
                key={index} 
                className="card recommendation-card"
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <h3>{item.title}</h3>
                <p>
                  <em>Why it helps:</em> {item.why_it_helps}
                </p>
                <ul>
                  {item.steps.map((step, stepIndex) => (
                    <li key={stepIndex}>{step}</li>
                  ))}
                </ul>
                <p className="meta">
                  {item.time_estimate} • {item.difficulty}
                </p>
                {hoveredIndex === index && user && (
                  <div className="save-button-overlay">
                    <button 
                      className="save-to-toolkit-button"
                      onClick={() => handleSave(item, index)}
                      disabled={savedItems.has(index)}
                    >
                      {savedItems.has(index) ? '✓ Saved to Toolkit' : 'Save to Toolkit'}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      <div className="button-container">
        <button className="primary-button start-over-button" onClick={onRestartQuiz}>
          Start Over
        </button>
        <button className="primary-button back-to-home-button" onClick={onBackToHome}>
          Back to Home
        </button>
      </div>
    </div>
  )
}

export default Results

