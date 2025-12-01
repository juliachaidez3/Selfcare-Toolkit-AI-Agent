import { useState } from 'react'
import { recordFeedback } from '../utils/userMemory'

function ActionFeedback({ actionId, onClose }) {
  const [rating, setRating] = useState(0)
  const [helpful, setHelpful] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async () => {
    if (rating === 0 && helpful === null) {
      // User didn't provide any feedback, just close
      onClose()
      return
    }

    try {
      await recordFeedback(actionId, rating || null, helpful)
      setSubmitted(true)
      setTimeout(() => {
        onClose()
      }, 1000)
    } catch (error) {
      console.error('Error submitting feedback:', error)
      console.error('Failed to submit feedback. Please try again.')
    }
  }

  if (submitted) {
    return (
      <div className="action-feedback">
        <p className="feedback-thanks">Thank you for your feedback! 🙏</p>
      </div>
    )
  }

  return (
    <div className="action-feedback">
      <p className="feedback-question">How helpful was this suggestion?</p>
      
      <div className="feedback-options">
        {/* Star rating */}
        <div className="star-rating">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              className={`star-button ${rating >= star ? 'active' : ''}`}
              onClick={() => setRating(star)}
              type="button"
            >
              ⭐
            </button>
          ))}
        </div>

        {/* Binary feedback */}
        <div className="binary-feedback">
          <button
            className={`feedback-button ${helpful === true ? 'active' : ''}`}
            onClick={() => setHelpful(true)}
            type="button"
          >
            ✓ This helped
          </button>
          <button
            className={`feedback-button ${helpful === false ? 'active' : ''}`}
            onClick={() => setHelpful(false)}
            type="button"
          >
            ✗ Not helpful
          </button>
        </div>
      </div>

      <div className="feedback-actions">
        <button className="feedback-submit-button" onClick={handleSubmit}>
          Submit
        </button>
        <button className="feedback-skip-button" onClick={onClose}>
          Skip
        </button>
      </div>
    </div>
  )
}

export default ActionFeedback

