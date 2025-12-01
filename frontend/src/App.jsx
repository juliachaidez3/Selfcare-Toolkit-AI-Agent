import { useState, useEffect, useRef } from 'react'
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
import Navbar from './components/Navbar'

function App() {
  const [user, setUser] = useState(null)
  const [authView, setAuthView] = useState('landing') // 'landing', 'signup', 'login'
  const [currentView, setCurrentView] = useState('landing') // 'landing', 'dashboard', 'quiz', 'loading', 'results', 'toolkit'
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
  const [showToolkit, setShowToolkit] = useState(false) // Track if toolkit view is shown
  const previousUserRef = useRef(null) // Track previous user state to detect sign-up

  // Function to save quiz data when user signs up after taking quiz
  const handleSaveQuizData = async (quizDataToSave, userId) => {
    // Save quiz data when user signs up after taking quiz
    if (results && results.length > 0) {
      try {
        await saveQuizToFirestore(userId, quizDataToSave, results)
        console.log('Pending quiz data saved to Firestore after sign-up')
      } catch (saveError) {
        console.error('Error saving pending quiz to Firestore:', saveError)
      }
    }
  }

  // Check authentication state on mount
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      const previousUser = previousUserRef.current
      const wasUnauthenticated = !previousUser && !!currentUser // Ensure boolean result
      
      // Update ref before setting state
      previousUserRef.current = currentUser
      setUser(currentUser)
      setLoading(false)
      
      if (currentUser) {
        setAuthView(null) // User is authenticated, hide auth views
        
        // Always navigate to dashboard when user authenticates (login or signup)
        // Check if user just authenticated (was not authenticated before) or is on auth-related views
        if (!previousUser || wasUnauthenticated || currentView === 'landing' || currentView === 'signup' || currentView === 'login') {
          setCurrentView('dashboard')
        }
      } else {
        // User is not authenticated (logged out)
        // Always go to landing page when user logs out
        setCurrentView('landing')
        setAuthView('landing')
      }
    })

    return () => unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      // Reset all state
      setCurrentView('landing')
      setAuthView('landing')
      setQuizData({
        struggle: '',
        mood: '',
        focus: '',
        copingPreferences: [],
        energyLevel: ''
      })
      setResults(null)
      setError(null)
      setShowToolkit(false)
    } catch (err) {
      console.error('Logout error:', err)
    }
  }

  const handleStartQuiz = () => {
    // Only allow authenticated users to take the quiz
    if (!user) {
      // Redirect to sign up if not authenticated
      setAuthView('signup')
      return
    }
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

  const handleExitQuiz = () => {
    // Go back to previous view without saving
    if (user) {
      setCurrentView('dashboard')
    } else {
      setCurrentView('landing')
      setAuthView('landing')
    }
    // Clear quiz data
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
          
          // Save quiz data and results to Firestore (user must be authenticated to take quiz)
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
    if (user) {
      setCurrentView('dashboard')
    } else {
      setCurrentView('landing')
      setAuthView('landing')
    }
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

  const handleBackToDashboard = () => {
    setCurrentView('dashboard')
    setShowToolkit(false) // Also close toolkit view if open
  }

  const handleViewToolkit = () => {
    setCurrentView('toolkit')
    setShowToolkit(false)
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
      // Validate and sanitize recommendations - ensure they're plain objects
      const sanitizedRecommendations = (recommendations || []).map(rec => {
        // Create a clean object with only the fields we need
        return {
          title: rec.title || '',
          why_it_helps: rec.why_it_helps || '',
          steps: Array.isArray(rec.steps) ? rec.steps : [],
          time_estimate: rec.time_estimate || '',
          difficulty: rec.difficulty || ''
        }
      })

      // Validate quiz data
      const sanitizedQuizData = {
        struggle: quizData?.struggle || '',
        mood: quizData?.mood || '',
        focus: quizData?.focus || '',
        copingPreferences: Array.isArray(quizData?.copingPreferences) ? quizData.copingPreferences : [],
        energyLevel: quizData?.energyLevel || ''
      }

      const quizRecord = {
        userId: userId,
        quizData: sanitizedQuizData,
        recommendations: sanitizedRecommendations,
        createdAt: serverTimestamp(),
        completedAt: serverTimestamp()
      }

      // Save to 'quizzes' collection
      await addDoc(collection(db, 'quizzes'), quizRecord)
      console.log('Quiz data saved successfully to Firestore')
    } catch (error) {
      console.error('Error saving quiz to Firestore:', error)
      console.error('Error details:', {
        code: error.code,
        message: error.message,
        stack: error.stack
      })
      // Don't throw - just log the error so the user can still see results
      // The error might be due to Firestore rules or network issues
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

  // Function to execute agent actions
  const handleExecuteAction = async (action, userId) => {
    try {
      const response = await fetch('/api/execute_action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: action,
          userId: userId
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }

      const result = await response.json()
      return result
    } catch (error) {
      console.error('Error executing action:', error)
      return {
        success: false,
        message: error.message || 'Failed to execute action'
      }
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

  // Show views based on currentView, not just auth state
  return (
    <div className="container">
      {/* Navbar - shown on all pages */}
      <Navbar
        user={user}
        currentView={currentView}
        onLogout={handleLogout}
        onBackToDashboard={handleBackToDashboard}
        onLogin={handleLogin}
        onExitQuiz={handleExitQuiz}
        showToolkit={showToolkit}
        authView={authView}
      />
      
      {/* Landing page - shown when not authenticated and on landing view */}
      {!user && authView === 'landing' && currentView === 'landing' && (
        <Landing 
          onSignUp={handleSignUp} 
          onLogin={handleLogin}
        />
      )}

      {/* Auth views - signup/login */}
      {!user && authView === 'signup' && (
        <SignUp onBack={handleAuthBack} onSuccess={handleAuthSuccess} />
      )}
      {!user && authView === 'login' && (
        <Login onBack={handleAuthBack} onSuccess={handleAuthSuccess} />
      )}

      {/* Quiz view - available to both authenticated and unauthenticated users */}
      {currentView === 'quiz' && (
        <Quiz
          quizData={quizData}
          onUpdateQuizData={handleUpdateQuizData}
          onGenerateToolkit={handleGenerateToolkit}
          onExit={handleExitQuiz}
        />
      )}

      {/* Loading view */}
      {currentView === 'loading' && (
        <Loading />
      )}

      {/* Results view - available to both authenticated and unauthenticated users */}
      {currentView === 'results' && (
        <Results
          results={results}
          error={error}
          onRestartQuiz={handleRestartQuiz}
          onBackToHome={handleBackToHome}
          onSaveToToolkit={handleSaveToToolkit}
          user={user}
          onSignUp={handleSignUp}
        />
      )}

      {/* Dashboard - only for authenticated users */}
      {user && currentView === 'dashboard' && (
        <Dashboard 
          userName={getUserName()} 
          onStartQuiz={handleStartQuiz}
          onLogout={handleLogout}
          userId={user?.uid}
          onExecuteAction={handleExecuteAction}
          onShowToolkitChange={setShowToolkit}
          externalShowToolkit={showToolkit}
          onViewToolkit={handleViewToolkit}
        />
      )}

      {user && currentView === 'toolkit' && (
        <Dashboard 
          userName={getUserName()} 
          onStartQuiz={handleStartQuiz}
          onLogout={handleLogout}
          userId={user?.uid}
          onExecuteAction={handleExecuteAction}
          onShowToolkitChange={setShowToolkit}
          externalShowToolkit={true}
          onViewToolkit={handleViewToolkit}
          showToolkitOnly={true}
        />
      )}

    </div>
  )
}

export default App
