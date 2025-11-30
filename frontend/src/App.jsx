import { useState, useEffect } from 'react'
import { onAuthStateChanged, signOut } from 'firebase/auth'
import { collection, addDoc, serverTimestamp } from 'firebase/firestore'
import { auth, db } from './firebase/config'
import Landing from './components/Landing'
import SignUp from './components/SignUp'
import Login from './components/Login'
import Dashboard from './components/Dashboard'
import Quiz from './components/Quiz'
import Loading from './components/Loading'
import Results from './components/Results'

function App() {
  const [user, setUser] = useState(null)
  const [authView, setAuthView] = useState('landing') // 'landing', 'signup', 'login'
  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard', 'quiz', 'loading', 'results'
  const [quizData, setQuizData] = useState({
    struggle: '',
    mood: '',
    focus: '',
    copingPreferences: [],
    energyLevel: ''
  })
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  // Check authentication state on mount
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser)
      setLoading(false)
      if (currentUser) {
        setAuthView(null) // User is authenticated, hide auth views
        setCurrentView('dashboard')
      } else {
        setAuthView('landing') // User is not authenticated, show landing
      }
    })

    return () => unsubscribe()
  }, [])

  const handleSignUp = () => {
    setAuthView('signup')
  }

  const handleLogin = () => {
    setAuthView('login')
  }

  const handleAuthBack = () => {
    setAuthView('landing')
  }

  const handleAuthSuccess = () => {
    // User is now authenticated, auth state change will handle the rest
    setAuthView(null)
  }

  const handleLogout = async () => {
    try {
      await signOut(auth)
      setCurrentView('dashboard')
      setQuizData({
        struggle: '',
        mood: '',
        focus: '',
        copingPreferences: [],
        energyLevel: ''
      })
      setResults(null)
      setError(null)
    } catch (err) {
      console.error('Logout error:', err)
    }
  }

  const handleStartQuiz = () => {
    setCurrentView('quiz')
    setQuizData({
      struggle: '',
      mood: '',
      focus: '',
      copingPreferences: [],
      energyLevel: ''
    })
    setResults(null)
    setError(null)
  }

  const handleUpdateQuizData = (field, value) => {
    setQuizData(prev => ({
      ...prev,
      [field]: value
    }))
  }

  const handleGenerateToolkit = async () => {
    setCurrentView('loading')
    setError(null)

    try {
      const response = await fetch('/api/toolkit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          struggle: quizData.struggle,
          mood: quizData.mood,
          focus: quizData.focus,
          copingPreferences: quizData.copingPreferences,
          energyLevel: quizData.energyLevel
        })
      })

      if (!response.ok) {
        // Try to extract error message from FastAPI error response
        let errorMsg = `HTTP error! status: ${response.status}`
        try {
          const errorData = await response.json()
          errorMsg = errorData.detail?.error || errorData.detail || errorData.error || errorMsg
        } catch (e) {
          // If JSON parsing fails, use default message
        }
        throw new Error(errorMsg)
      }

      const data = await response.json()

      if (data.status === 'crisis') {
        setError(data.message)
        setCurrentView('results')
        return
      }

      if (data.error) {
        setError(data.error)
        setCurrentView('results')
      } else {
        // Extract recommendations from response
        let recommendations = []
        
        if (Array.isArray(data)) {
          recommendations = data
        } else if (typeof data === 'object' && data !== null) {
          for (const key in data) {
            if (Array.isArray(data[key]) && data[key].length > 0) {
              recommendations = data[key]
              break
            }
          }
        }

        if (recommendations.length > 0) {
          setResults(recommendations)
          
          // Save quiz data and results to Firestore
          if (user) {
            try {
              await saveQuizToFirestore(user.uid, quizData, recommendations)
              console.log('Quiz data saved to Firestore')
            } catch (saveError) {
              console.error('Error saving quiz to Firestore:', saveError)
              // Don't block the user from seeing results if save fails
            }
          }
          
          setCurrentView('results')
        } else {
          setError('No recommendations generated. Please try again.')
          setCurrentView('results')
        }
      }
    } catch (err) {
      console.error('Error:', err)
      setError(err.message)
      setCurrentView('results')
    }
  }

  const handleRestartQuiz = () => {
    setCurrentView('quiz')
    setQuizData({
      struggle: '',
      mood: '',
      focus: '',
      copingPreferences: [],
      energyLevel: ''
    })
    setResults(null)
    setError(null)
  }

  const handleBackToHome = () => {
    setCurrentView('dashboard')
    setQuizData({
      struggle: '',
      mood: '',
      focus: '',
      copingPreferences: [],
      energyLevel: ''
    })
    setResults(null)
    setError(null)
  }

  // Get user's name from email (part before @) or use displayName
  const getUserName = () => {
    if (!user) return null
    if (user.displayName) return user.displayName
    if (user.email) {
      const emailName = user.email.split('@')[0]
      // Capitalize first letter
      return emailName.charAt(0).toUpperCase() + emailName.slice(1)
    }
    return null
  }

  // Function to save quiz data and results to Firestore
  const saveQuizToFirestore = async (userId, quizData, recommendations) => {
    try {
      const quizRecord = {
        userId: userId,
        quizData: {
          struggle: quizData.struggle,
          mood: quizData.mood,
          focus: quizData.focus,
          copingPreferences: quizData.copingPreferences,
          energyLevel: quizData.energyLevel
        },
        recommendations: recommendations,
        createdAt: serverTimestamp(),
        completedAt: serverTimestamp()
      }

      // Save to 'quizzes' collection
      await addDoc(collection(db, 'quizzes'), quizRecord)
    } catch (error) {
      console.error('Error saving quiz to Firestore:', error)
      throw error
    }
  }

  // Function to save individual recommendation to user's toolkit
  const handleSaveToToolkit = async (recommendation) => {
    if (!user) {
      throw new Error('User must be logged in to save to toolkit')
    }

    try {
      const toolkitItem = {
        userId: user.uid,
        recommendation: recommendation,
        savedAt: serverTimestamp()
      }

      // Save to 'toolkit' collection
      await addDoc(collection(db, 'toolkit'), toolkitItem)
      console.log('Recommendation saved to toolkit')
    } catch (error) {
      console.error('Error saving to toolkit:', error)
      throw error
    }
  }

  // Show loading while checking auth
  if (loading) {
    return (
      <div className="container">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <div className="loading-text">Loading...</div>
        </div>
      </div>
    )
  }

  // Show authentication views if user is not authenticated
  if (!user) {
    return (
      <div className="container">
        {authView === 'landing' && (
          <Landing onSignUp={handleSignUp} onLogin={handleLogin} />
        )}
        {authView === 'signup' && (
          <SignUp onBack={handleAuthBack} onSuccess={handleAuthSuccess} />
        )}
        {authView === 'login' && (
          <Login onBack={handleAuthBack} onSuccess={handleAuthSuccess} />
        )}
        <p className="disclaimer">
          This is general wellness guidance, not medical advice. If you're in crisis, contact campus counseling or emergency services.
        </p>
      </div>
    )
  }

  // User is authenticated, show main app
  return (
    <div className="container">
      {/* {user && (
        <div className="user-info">
          <p>Logged in as: <strong>{user.email}</strong></p>
          <button className="logout-button" onClick={handleLogout}>
            Log Out
          </button>
        </div>
      )} */}

      {currentView === 'dashboard' && (
        <Dashboard 
          userName={getUserName()} 
          onStartQuiz={handleStartQuiz}
          onLogout={handleLogout}
          userId={user?.uid}
        />
      )}
      
      {currentView === 'quiz' && (
        <Quiz
          quizData={quizData}
          onUpdateQuizData={handleUpdateQuizData}
          onGenerateToolkit={handleGenerateToolkit}
        />
      )}

      {currentView === 'loading' && (
        <Loading />
      )}

      {currentView === 'results' && (
        <Results
          results={results}
          error={error}
          onRestartQuiz={handleRestartQuiz}
          onBackToHome={handleBackToHome}
          onSaveToToolkit={handleSaveToToolkit}
          user={user}
        />
      )}

      <p className="disclaimer">
        This is general wellness guidance, not medical advice. If you're in crisis, contact campus counseling or emergency services.
      </p>
    </div>
  )
}

export default App
