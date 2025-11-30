import { useState, useEffect } from 'react'
import { collection, query, where, getDocs, orderBy, deleteDoc, doc } from 'firebase/firestore'
import { db } from '../firebase/config'

function Dashboard({ userName, onStartQuiz, onLogout, userId }) {
  const [toolkitItems, setToolkitItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [showToolkit, setShowToolkit] = useState(false)

  useEffect(() => {
    if (userId) {
      fetchToolkitItems()
    }
  }, [userId])

  const fetchToolkitItems = async () => {
    if (!userId) return
    
    try {
      setLoading(true)
      const toolkitRef = collection(db, 'toolkit')
      
      // Try with orderBy first, fallback to just where if index doesn't exist
      let querySnapshot
      try {
        const q = query(
          toolkitRef,
          where('userId', '==', userId),
          orderBy('savedAt', 'desc')
        )
        querySnapshot = await getDocs(q)
      } catch (indexError) {
        // If composite index doesn't exist, query without orderBy
        if (indexError.code === 'failed-precondition') {
          console.warn('Composite index may not exist, querying without orderBy')
          const q = query(
            toolkitRef,
            where('userId', '==', userId)
          )
          querySnapshot = await getDocs(q)
        } else {
          throw indexError
        }
      }
      
      const items = []
      querySnapshot.forEach((doc) => {
        items.push({ id: doc.id, ...doc.data() })
      })
      
      // Sort manually if we couldn't use orderBy
      if (items.length > 0 && items[0].savedAt) {
        items.sort((a, b) => {
          const aTime = a.savedAt?.toMillis?.() || 0
          const bTime = b.savedAt?.toMillis?.() || 0
          return bTime - aTime // Descending order
        })
      }
      
      setToolkitItems(items)
    } catch (error) {
      console.error('Error fetching toolkit items:', error)
      // If it's a permissions error, show a helpful message
      if (error.code === 'permission-denied') {
        console.error('Firestore permission denied. Please update your Firestore security rules to include the toolkit collection. See FIRESTORE_RULES_TOOLKIT.md for instructions.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteToolkitItem = async (itemId) => {
    try {
      await deleteDoc(doc(db, 'toolkit', itemId))
      setToolkitItems(prev => prev.filter(item => item.id !== itemId))
    } catch (error) {
      console.error('Error deleting toolkit item:', error)
      alert('Failed to delete item. Please try again.')
    }
  }

  return (
    <div className="quiz-page active dashboard-page">
      <div className="dashboard-header">
        <h1>Welcome back{userName ? `, ${userName}` : ''}!</h1>
        <button className="dashboard-logout-button" onClick={onLogout}>
          Log Out
        </button>
      </div>
      
      {!showToolkit ? (
        <>
          <p className="dashboard-subtitle">How are you feeling today?</p>
          <div className="dashboard-buttons">
            <button className="primary-button" onClick={onStartQuiz}>
              Take the Quiz
            </button>
            {toolkitItems.length > 0 && (
              <button 
                className="secondary-button" 
                onClick={() => setShowToolkit(true)}
              >
                View My Toolkit ({toolkitItems.length})
              </button>
            )}
          </div>
        </>
      ) : (
        <div className="toolkit-view">
          <div className="toolkit-header">
            <h2>My Saved Toolkit</h2>
            <button 
              className="back-button" 
              onClick={() => setShowToolkit(false)}
            >
              Back to Home
            </button>
          </div>
          
          {loading ? (
            <div className="loading-text">Loading your toolkit...</div>
          ) : toolkitItems.length === 0 ? (
            <div className="empty-toolkit">
              <p>Your toolkit is empty. Save recommendations from quiz results to build your toolkit!</p>
              <button className="primary-button" onClick={onStartQuiz}>
                Take the Quiz
              </button>
            </div>
          ) : (
            <div className="toolkit-container">
              {toolkitItems.map((item) => (
                <div key={item.id} className="toolkit-card">
                  <button 
                    className="delete-toolkit-item"
                    onClick={() => handleDeleteToolkitItem(item.id)}
                    title="Remove from toolkit"
                  >
                    ×
                  </button>
                  <h3>{item.recommendation.title}</h3>
                  <p>
                    <em>Why it helps:</em> {item.recommendation.why_it_helps}
                  </p>
                  <ul>
                    {item.recommendation.steps.map((step, stepIndex) => (
                      <li key={stepIndex}>{step}</li>
                    ))}
                  </ul>
                  <p className="meta">
                    {item.recommendation.time_estimate} • {item.recommendation.difficulty}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default Dashboard

