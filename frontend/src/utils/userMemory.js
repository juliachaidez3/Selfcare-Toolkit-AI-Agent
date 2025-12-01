import { collection, doc, setDoc, getDoc, query, where, getDocs, orderBy, limit, updateDoc, serverTimestamp } from 'firebase/firestore'
import { db } from '../firebase/config'

/**
 * Get user profile with preferences, likes, dislikes, and constraints
 */
export async function getUserProfile(userId) {
  try {
    const docRef = doc(db, 'user_profiles', userId)
    const docSnap = await getDoc(docRef)
    if (docSnap.exists()) {
      return docSnap.data()
    }
    return {}
  } catch (error) {
    console.error('Error fetching user profile:', error)
    return {}
  }
}

/**
 * Update user profile
 */
export async function updateUserProfile(userId, updates) {
  try {
    const docRef = doc(db, 'user_profiles', userId)
    await setDoc(docRef, {
      ...updates,
      updatedAt: serverTimestamp()
    }, { merge: true })
  } catch (error) {
    console.error('Error updating user profile:', error)
    throw error
  }
}

/**
 * Record an action in agent history
 */
export async function recordAction(userId, actionType, actionMessage, outcome, actionParams = {}) {
  try {
    const docRef = doc(collection(db, 'agent_history'))
    await setDoc(docRef, {
      userId,
      actionType,
      actionMessage,
      outcome, // 'confirmed' or 'dismissed'
      actionParams,
      timestamp: serverTimestamp()
    })
    return docRef.id // Return the document ID for feedback
  } catch (error) {
    console.error('Error recording action:', error)
    throw error
  }
}

/**
 * Get recent actions (last N)
 */
export async function getRecentActions(userId, actionLimit = 7) {
  try {
    // Try query with index first
    const q = query(
      collection(db, 'agent_history'),
      where('userId', '==', userId),
      orderBy('timestamp', 'desc'),
      limit(actionLimit)
    )
    const querySnapshot = await getDocs(q)
    const actions = []
    querySnapshot.forEach((doc) => {
      actions.push({ id: doc.id, ...doc.data() })
    })
    return actions
  } catch (error) {
    // If index error, fall back to querying without orderBy and sorting manually
    if (error.code === 'failed-precondition' && error.message.includes('index')) {
      console.warn('Composite index not found, fetching without orderBy and sorting manually')
      try {
        const q = query(
          collection(db, 'agent_history'),
          where('userId', '==', userId)
        )
        const querySnapshot = await getDocs(q)
        const actions = []
        querySnapshot.forEach((doc) => {
          const data = doc.data()
          actions.push({ id: doc.id, ...data })
        })
        // Sort manually by timestamp (descending)
        actions.sort((a, b) => {
          const aTime = a.timestamp?.toMillis?.() || 0
          const bTime = b.timestamp?.toMillis?.() || 0
          return bTime - aTime // Descending order
        })
        // Return only the requested limit
        return actions.slice(0, actionLimit)
      } catch (fallbackError) {
        console.error('Error fetching recent actions (fallback):', fallbackError)
        return []
      }
    }
    console.error('Error fetching recent actions:', error)
    return []
  }
}

/**
 * Record feedback for an action
 */
export async function recordFeedback(actionId, rating, helpful = null) {
  try {
    const docRef = doc(db, 'agent_history', actionId)
    await updateDoc(docRef, {
      rating,
      helpful,
      feedbackTimestamp: serverTimestamp()
    })
  } catch (error) {
    console.error('Error recording feedback:', error)
    throw error
  }
}

/**
 * Calculate action statistics for the agent prompt
 */
export async function getActionStatistics(userId) {
  try {
    const q = query(
      collection(db, 'agent_history'),
      where('userId', '==', userId)
    )
    const querySnapshot = await getDocs(q)
    
    const actions = []
    querySnapshot.forEach((doc) => {
      actions.push(doc.data())
    })
    
    if (actions.length === 0) {
      return {}
    }
    
    // Calculate statistics
    const actionCounts = {}
    const confirmedCounts = {}
    const dismissedCounts = {}
    const ratingsByType = {}
    
    actions.forEach((action) => {
      const actionType = action.actionType || 'unknown'
      const outcome = action.outcome || 'unknown'
      const rating = action.rating
      
      // Count actions
      actionCounts[actionType] = (actionCounts[actionType] || 0) + 1
      
      // Count outcomes
      if (outcome === 'confirmed') {
        confirmedCounts[actionType] = (confirmedCounts[actionType] || 0) + 1
      } else if (outcome === 'dismissed') {
        dismissedCounts[actionType] = (dismissedCounts[actionType] || 0) + 1
      }
      
      // Collect ratings
      if (rating != null) {
        if (!ratingsByType[actionType]) {
          ratingsByType[actionType] = []
        }
        ratingsByType[actionType].push(rating)
      }
    })
    
    // Calculate acceptance rates
    const acceptanceRates = {}
    Object.keys(actionCounts).forEach((actionType) => {
      const total = actionCounts[actionType]
      const confirmed = confirmedCounts[actionType] || 0
      if (total > 0) {
        acceptanceRates[actionType] = confirmed / total
      }
    })
    
    // Calculate average ratings
    const averageRatings = {}
    Object.keys(ratingsByType).forEach((actionType) => {
      const ratings = ratingsByType[actionType]
      if (ratings.length > 0) {
        averageRatings[actionType] = ratings.reduce((a, b) => a + b, 0) / ratings.length
      }
    })
    
    // Infer preferences
    const preferences = []
    Object.keys(acceptanceRates).forEach((actionType) => {
      const rate = acceptanceRates[actionType]
      const actionName = actionType.replace(/_/g, ' ')
      if (rate >= 0.7) {
        preferences.push(`User tends to accept ${actionName} suggestions`)
      } else if (rate <= 0.3) {
        preferences.push(`User tends to decline ${actionName} suggestions`)
      }
    })
    
    // Add rating-based preferences
    Object.keys(averageRatings).forEach((actionType) => {
      const avgRating = averageRatings[actionType]
      const actionName = actionType.replace(/_/g, ' ')
      if (avgRating >= 4.0) {
        preferences.push(`User rates ${actionName} suggestions highly (${avgRating.toFixed(1)}/5)`)
      } else if (avgRating <= 2.0) {
        preferences.push(`User rates ${actionName} suggestions poorly (${avgRating.toFixed(1)}/5)`)
      }
    })
    
    return {
      action_counts: actionCounts,
      acceptance_rates: acceptanceRates,
      average_ratings: averageRatings,
      preferences,
      total_actions: actions.length
    }
  } catch (error) {
    console.error('Error calculating action statistics:', error)
    return {}
  }
}

