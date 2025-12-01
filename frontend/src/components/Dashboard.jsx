import { useState, useEffect } from 'react'
import { collection, query, where, getDocs, orderBy, deleteDoc, doc, limit } from 'firebase/firestore'
import { db } from '../firebase/config'
import { getUserProfile, getRecentActions, getActionStatistics, recordAction } from '../utils/userMemory'
import ActionFeedback from './ActionFeedback'

function Dashboard({ userName, onStartQuiz, onLogout, userId, onExecuteAction, onShowToolkitChange, externalShowToolkit, onViewToolkit, showToolkitOnly = false }) {
  const [toolkitItems, setToolkitItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [showToolkit, setShowToolkit] = useState(false)
  
  // Sync showToolkit state with parent
  const handleShowToolkitChange = (value) => {
    setShowToolkit(value)
    if (onShowToolkitChange) {
      onShowToolkitChange(value)
    }
  }
  
  // Sync with external showToolkit prop (when parent closes it)
  useEffect(() => {
    if (externalShowToolkit !== undefined && externalShowToolkit !== showToolkit) {
      setShowToolkit(externalShowToolkit)
    }
  }, [externalShowToolkit])
  
  const [agentSuggestions, setAgentSuggestions] = useState([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [lastQuiz, setLastQuiz] = useState(null)
  const [userLocation, setUserLocation] = useState(null)
  const [showTimePicker, setShowTimePicker] = useState(false)
  const [pendingCalendarAction, setPendingCalendarAction] = useState(null)
  const [selectingTime, setSelectingTime] = useState(false) // Track when a time is being selected
  const [selectedTimeValue, setSelectedTimeValue] = useState(null) // Track the time value selected by the user
  const [userProfile, setUserProfile] = useState(null)
  const [recentActions, setRecentActions] = useState([])
  const [actionStats, setActionStats] = useState(null)
  const [showFeedback, setShowFeedback] = useState(false)
  const [pendingFeedbackActionId, setPendingFeedbackActionId] = useState(null)
  const [executingAction, setExecutingAction] = useState(null) // Track which specific action is being executed (the action object itself)
  const [calendarEvents, setCalendarEvents] = useState([])
  const [journalEntries, setJournalEntries] = useState([])
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [loadingJournals, setLoadingJournals] = useState(false)
  const [freeSlots, setFreeSlots] = useState([])
  const [loadingFreeSlots, setLoadingFreeSlots] = useState(false)
  const [customDateTime, setCustomDateTime] = useState('') // Track custom datetime input value
  const [conflictError, setConflictError] = useState(null) // Track conflict error message

  useEffect(() => {
    if (userId) {
      console.log('Dashboard: Fetching toolkit items for userId:', userId)
      // Fetch immediately for responsive UI
      fetchToolkitItems()
      fetchLastQuiz()
      requestUserLocation()
      
      // Also fetch again after delays to catch any items that were just saved
      const refreshTimer1 = setTimeout(() => {
        console.log('Dashboard: Refreshing toolkit items (first refresh)')
        fetchToolkitItems()
      }, 2000) // 2 second delay
      
      const refreshTimer2 = setTimeout(() => {
        console.log('Dashboard: Refreshing toolkit items (second refresh)')
        fetchToolkitItems()
      }, 4000) // 4 second delay
      
      return () => {
        clearTimeout(refreshTimer1)
        clearTimeout(refreshTimer2)
      }
    }
  }, [userId])

  const requestUserLocation = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setUserLocation({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude
          })
        },
        (error) => {
          console.log('Location permission denied or unavailable:', error.message)
          // Continue without location - weather suggestions just won't be available
        },
        {
          enableHighAccuracy: false,
          timeout: 5000,
          maximumAge: 300000 // Cache for 5 minutes
        }
      )
    }
  }

  const fetchLastQuiz = async () => {
    if (!userId) return
    
    try {
      const quizzesRef = collection(db, 'quizzes')
      
      // Try with orderBy first, fallback to just where if index doesn't exist
      let querySnapshot
      try {
        const q = query(
          quizzesRef,
          where('userId', '==', userId),
          orderBy('completedAt', 'desc'),
          limit(1)
        )
        querySnapshot = await getDocs(q)
      } catch (indexError) {
        // If composite index doesn't exist, query without orderBy
        if (indexError.code === 'failed-precondition') {
          console.warn('Composite index may not exist for quizzes, querying without orderBy')
          const q = query(
            quizzesRef,
            where('userId', '==', userId)
          )
          querySnapshot = await getDocs(q)
        } else {
          throw indexError
        }
      }
      
      if (!querySnapshot.empty) {
        let quizDoc = querySnapshot.docs[0]
        
        // If we queried without orderBy, find the most recent one manually
        if (querySnapshot.docs.length > 1) {
          const docs = querySnapshot.docs.map(doc => ({
            id: doc.id,
            data: doc.data(),
            completedAt: doc.data().completedAt
          }))
          
          // Sort by completedAt descending
          docs.sort((a, b) => {
            const aTime = a.completedAt?.toMillis?.() || 0
            const bTime = b.completedAt?.toMillis?.() || 0
            return bTime - aTime
          })
          
          quizDoc = querySnapshot.docs.find(doc => doc.id === docs[0].id) || querySnapshot.docs[0]
        }
        
        const quizData = quizDoc.data()
        setLastQuiz({
          ...quizData.quizData,
          completedAt: quizData.completedAt
        })
      }
    } catch (error) {
      console.error('Error fetching last quiz:', error)
      // Don't block the app if this fails
    }
  }

  const fetchAgentSuggestions = async (replaceAll = false) => {
    if (!userId) {
      setLoadingSuggestions(false)
      return
    }
    
    try {
      setLoadingSuggestions(true)
      
      // Calculate days since last quiz
      let daysSinceLastQuiz = null
      if (lastQuiz && lastQuiz.completedAt) {
        const lastQuizDate = lastQuiz.completedAt.toDate()
        const now = new Date()
        const diffTime = Math.abs(now - lastQuizDate)
        daysSinceLastQuiz = Math.floor(diffTime / (1000 * 60 * 60 * 24))
      }
      
      // Ensure userProfile, recentActions, and actionStats are not null (can be empty objects/arrays)
      const safeUserProfile = userProfile || {}
      const safeRecentActions = recentActions || []
      const safeActionStats = actionStats || {}
      
      const response = await fetch('/api/agent_suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lastQuiz: lastQuiz ? {
            struggle: lastQuiz.struggle,
            mood: lastQuiz.mood,
            focus: lastQuiz.focus,
            energyLevel: lastQuiz.energyLevel
          } : null,
          toolkitCount: toolkitItems.length,
          daysSinceLastQuiz: daysSinceLastQuiz,
          latitude: userLocation?.latitude || null,
          longitude: userLocation?.longitude || null,
          userProfile: safeUserProfile,
          recentActions: safeRecentActions,
          actionStats: safeActionStats
        })
      })
      
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
      
      const data = await response.json()
      const actions = data.actions || []
      
      // If no actions returned, show error state
      if (actions.length === 0) {
        console.warn('Agent returned 0 suggestions - this should be rare')
        // Set a fallback suggestion to ensure user always sees something
        if (replaceAll || agentSuggestions.length === 0) {
          setAgentSuggestions([{
            type: 'suggest_retake_quiz',
            message: 'How are you feeling today? Taking our self-care quiz can help identify what you need right now.',
            requires_confirmation: true,
            params: { reason: 'Regular check-ins help maintain wellbeing' }
          }])
        }
      } else {
        // If replaceAll is true or we have no suggestions, replace all
        // Otherwise, append new ones to fill up to 2 total
        // Log calendar actions to track time_window values
        actions.forEach((action, idx) => {
          if (action.type === 'create_calendar_block') {
            const timeWindow = action.params?.time_window
            const timeWindowType = timeWindow ? 
              (timeWindow.includes('T') && timeWindow.length > 16 ? 'ISO_DATETIME' : 'RELATIVE') : 
              'NOT_SET'
            console.log(`[Agent Suggestions] Calendar action ${idx + 1}:`, {
              message: action.message,
              duration_minutes: action.params?.duration_minutes,
              time_window: timeWindow,
              time_window_type: timeWindowType,
              purpose: action.params?.purpose,
              full_params: JSON.stringify(action.params)
            })
            
            // Warn if we still have a relative time_window
            if (timeWindowType === 'RELATIVE') {
              console.warn(`[Agent Suggestions] ⚠️ WARNING: Calendar action still has RELATIVE time_window: "${timeWindow}" - this should be an ISO datetime!`)
            }
          }
        })
        
        setAgentSuggestions(prev => {
          if (replaceAll || prev.length === 0) {
            // Replace all or initial load - set new suggestions (limit to 2)
            return actions.slice(0, 2)
          } else {
            // We have some suggestions, append new ones to reach 2 total
            const needed = 2 - prev.length
            const newActions = actions.slice(0, needed)
            return [...prev, ...newActions].slice(0, 2) // Ensure we never have more than 2
          }
        })
      }
    } catch (error) {
      console.error('Error fetching agent suggestions:', error)
      // On error, only add fallback if we have no suggestions
      if (agentSuggestions.length === 0) {
        setAgentSuggestions([{
          type: 'suggest_retake_quiz',
          message: 'We had trouble loading personalized suggestions. Would you like to take our self-care quiz to get started?',
          requires_confirmation: true,
          params: { reason: 'Get personalized recommendations' }
        }])
      }
    } finally {
      setLoadingSuggestions(false)
    }
  }

  // Fetch user memory (profile, recent actions, stats)
  const fetchUserMemory = async () => {
    if (!userId) return
    
    try {
      const [profile, actions, stats] = await Promise.all([
        getUserProfile(userId),
        getRecentActions(userId),
        getActionStatistics(userId)
      ])
      setUserProfile(profile || {})
      setRecentActions(actions || [])
      setActionStats(stats || {})
    } catch (error) {
      console.error('Error fetching user memory:', error)
      // Set defaults on error so suggestions can still load
      setUserProfile({})
      setRecentActions([])
      setActionStats({})
    }
  }

  // Fetch user memory on mount
  useEffect(() => {
    if (userId) {
      fetchUserMemory()
    }
  }, [userId])

  // Log when time picker opens
  useEffect(() => {
    if (showTimePicker && pendingCalendarAction) {
      const timeWindow = pendingCalendarAction.params?.time_window
      const timeWindowType = timeWindow ? 
        (timeWindow.includes('T') && timeWindow.length > 16 ? 'ISO_DATETIME' : 'RELATIVE') : 
        'NOT_SET'
      console.log('[Time Picker] Modal opened with action:', {
        purpose: pendingCalendarAction.params?.purpose,
        duration_minutes: pendingCalendarAction.params?.duration_minutes,
        time_window: timeWindow,
        time_window_type: timeWindowType,
        free_slots_available: freeSlots.length,
        loading_free_slots: loadingFreeSlots,
        full_action: JSON.stringify(pendingCalendarAction, null, 2)
      })
      
      if (timeWindowType === 'RELATIVE') {
        console.error(`[Time Picker] ⚠️ ERROR: Received RELATIVE time_window "${timeWindow}" from backend - should be ISO datetime!`)
      }
    }
  }, [showTimePicker, pendingCalendarAction, freeSlots.length, loadingFreeSlots])

  // Fetch calendar events and journal entries
  useEffect(() => {
    if (userId) {
      fetchCalendarEvents()
      fetchJournalEntries()
    }
  }, [userId])

  const fetchCalendarEvents = async () => {
    try {
      setLoadingEvents(true)
      const response = await fetch('/api/calendar_events')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setCalendarEvents(data.events || [])
    } catch (error) {
      console.error('Error fetching calendar events:', error)
      setCalendarEvents([])
    } finally {
      setLoadingEvents(false)
    }
  }

  const fetchJournalEntries = async () => {
    try {
      setLoadingJournals(true)
      const response = await fetch('/api/journal_entries')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setJournalEntries(data.entries || [])
    } catch (error) {
      console.error('Error fetching journal entries:', error)
      setJournalEntries([])
    } finally {
      setLoadingJournals(false)
    }
  }

  const fetchFreeSlots = async (durationMinutes, actionToUpdate = null) => {
    try {
      console.log(`[Free Slots] Fetching free slots for duration: ${durationMinutes} minutes`)
      setLoadingFreeSlots(true)
      const today = new Date().toISOString().split('T')[0]
      const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().split('T')[0]
      
      console.log(`[Free Slots] Requesting slots from ${today} to ${tomorrow}`)
      const response = await fetch(`/api/free_slots?start_date=today&end_date=${tomorrow}&duration_minutes=${durationMinutes}`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      const slots = data.free_slots || []
      console.log(`[Free Slots] Received ${slots.length} free slots:`, slots.map(s => ({
        start: s.start,
        duration: s.duration_minutes
      })))
      setFreeSlots(slots)
      
      // Use the provided action or the current pendingCalendarAction
      const action = actionToUpdate || pendingCalendarAction
      
      // If we have a calendar action and free slots, update the suggested time
      // Always update if time_window is not set or is a relative time (not ISO datetime)
      if (action && slots.length > 0) {
        const currentTimeWindow = action.params?.time_window
        // Check if current time_window is already an ISO datetime (from backend free slot lookup)
        const isAlreadyISO = currentTimeWindow && currentTimeWindow.includes('T') && currentTimeWindow.length > 16
        
        console.log(`[Free Slots] Calendar action time_window:`, {
          current: currentTimeWindow,
          isISO: isAlreadyISO,
          action_purpose: action.params?.purpose,
          source: action.params?.source,
          has_action_to_update: !!actionToUpdate
        })
        
        if (!isAlreadyISO) {
          // Use the first free slot as the suggested time
          const bestSlot = slots[0]
          console.log(`[Free Slots] Updating time_window from "${currentTimeWindow || 'NOT_SET'}" to ISO datetime: ${bestSlot.start}`)
          
          // Update the action's time_window to use the exact free slot time
          const updatedAction = {
            ...action,
            params: {
              ...action.params,
              time_window: bestSlot.start // Use the exact ISO datetime from free slot
            }
          }
          
          // Use functional update to ensure we're updating the latest state
          setPendingCalendarAction(prevAction => {
            if (prevAction && prevAction.params?.purpose === action.params?.purpose) {
              console.log(`[Free Slots] ✅ Updating pendingCalendarAction with ISO datetime time_window: ${bestSlot.start}`)
              return updatedAction
            }
            return prevAction
          })
          
          console.log(`[Free Slots] ✅ Updated action with ISO datetime time_window: ${bestSlot.start}`)
        } else {
          console.log(`[Free Slots] Time window already set to ISO datetime, not updating`)
        }
      } else if (action && slots.length === 0) {
        console.warn(`[Free Slots] ⚠️ No free slots found, but have calendar action. User will need to select a custom time.`)
      } else if (!action) {
        console.warn(`[Free Slots] ⚠️ No calendar action available to update`)
      }
    } catch (error) {
      console.error('[Free Slots] Error fetching free slots:', error)
      setFreeSlots([])
    } finally {
      setLoadingFreeSlots(false)
    }
  }

  // Fetch suggestions only on initial load or when we have no suggestions
  useEffect(() => {
    if (userId && !loading && agentSuggestions.length === 0) {
      // Only fetch if we don't have any suggestions yet
      // Wait a bit for data to be ready, then fetch suggestions
      const timer = setTimeout(() => {
        fetchAgentSuggestions(true) // true = replace all (initial load)
      }, 1500)
      return () => clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, loading, agentSuggestions.length]) // Only depend on userId, loading, and suggestion count

  const fetchToolkitItems = async () => {
    if (!userId) {
      console.log('Dashboard: Cannot fetch toolkit items - no userId')
      return
    }
    
    try {
      setLoading(true)
      console.log('Dashboard: Fetching toolkit items from Firestore for userId:', userId)
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
      
      console.log(`Dashboard: Fetched ${items.length} toolkit items`)
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
      console.error('Failed to delete item. Please try again.')
    }
  }

  const handleConfirmAction = async (action, customTime = null) => {
    // For calendar actions, show time picker first (unless customTime is provided)
    if (action.type === 'create_calendar_block' && !customTime) {
      console.log('[Calendar Action] Showing time picker for calendar action:', {
        message: action.message,
        duration_minutes: action.params?.duration_minutes,
        time_window: action.params?.time_window,
        time_window_type: action.params?.time_window ? 
          (action.params.time_window.includes('T') && action.params.time_window.length > 16 ? 'ISO_DATETIME (from backend)' : 'RELATIVE (from agent)') : 
          'NOT_SET (will be set by backend)',
        purpose: action.params?.purpose
      })
      setPendingCalendarAction(action)
      setShowTimePicker(true)
      // Fetch free slots for this duration to find the best suggested time
      const duration = action.params?.duration_minutes || 30
      console.log(`[Calendar Action] Fetching free slots for duration: ${duration} minutes`)
      // Pass the action directly to avoid closure issues
      await fetchFreeSlots(duration, action)
      return
    }

    try {
      // Set loading state - track the specific action object, not just the type
      setExecutingAction(action)
      console.log('Executing action:', action.type, 'with customTime:', customTime)

      // Update action params if custom time is provided
      const actionToExecute = customTime && action.type === 'create_calendar_block'
        ? {
            ...action,
            params: {
              ...action.params,
              time_window: customTime
            }
          }
        : action

      const result = await onExecuteAction(actionToExecute, userId)
      
      // Check for conflict error FIRST - before any other handling
      if (!result.success && result.conflict) {
        // Conflict detected - show error and keep time picker open
        setConflictError(result.message || 'This time conflicts with an existing event. Please choose another time.')
        setExecutingAction(null) // Clear loading state
        setSelectingTime(false) // Clear time selection loading
        setSelectedTimeValue(null) // Clear selected time
        // Keep time picker open so user can select another time
        // Don't close the time picker or clear pendingCalendarAction
        return // Exit early - don't run finally block logic that might close picker
      }
      
      if (result.success) {
        // Record confirmed action
        let actionId = null
        if (userId) {
          try {
            actionId = await recordAction(
              userId,
              actionToExecute.type,
              actionToExecute.message,
              'confirmed',
              actionToExecute.params
            )
            // Refresh user memory to update statistics
            fetchUserMemory()
          } catch (error) {
            // Log error but don't break the user experience
            // This is a non-critical operation - the action was still executed
            console.error('Error recording confirmed action (non-critical):', error)
            if (error.code === 'permission-denied') {
              console.warn('Firestore permission denied. Please add security rules for agent_history collection. See FIRESTORE_RULES_AGENT_HISTORY.md')
            }
          }
        }
        
        // Remove the suggestion from the list and fetch a replacement
        setAgentSuggestions(prev => prev.filter(a => a !== action))
        
        // Fetch a new suggestion to replace the one that was confirmed
        // Use a short delay to allow state to update
        setTimeout(() => {
          fetchAgentSuggestions(false) // false = append, don't replace all
        }, 500)
        
        // If there's a document URL (from journal entry), open it in a new tab
        if (result.data?.document_url) {
          window.open(result.data.document_url, '_blank')
          // Refresh journal entries after a short delay
          setTimeout(() => {
            fetchJournalEntries()
          }, 2000)
          // Show feedback UI after a short delay
          if (actionId) {
            setTimeout(() => {
              setPendingFeedbackActionId(actionId)
              setShowFeedback(true)
            }, 1500)
          } else {
            console.log(result.message || 'Journal entry created! Opening in a new tab...')
          }
        } 
        // If there's an HTML link (from calendar event), open it in a new tab
        else if (result.data?.html_link) {
          window.open(result.data.html_link, '_blank')
          // Clear the datetime input for next time
          setCustomDateTime('')
          // Close the time picker modal and clear loading states
          setShowTimePicker(false)
          setPendingCalendarAction(null)
          setSelectingTime(false)
          setSelectedTimeValue(null)
          setFreeSlots([])
          setConflictError(null)
          // Refresh calendar events after a short delay
          setTimeout(() => {
            fetchCalendarEvents()
          }, 2000)
          // Show feedback UI after a short delay
          if (actionId) {
            setTimeout(() => {
              setPendingFeedbackActionId(actionId)
              setShowFeedback(true)
            }, 1500)
          } else {
            console.log(result.message || 'Calendar event created! Opening in a new tab...')
          }
        } 
        else {
          // Show success message and feedback UI
          if (actionId) {
            setTimeout(() => {
              setPendingFeedbackActionId(actionId)
              setShowFeedback(true)
            }, 1000)
          } else {
            console.log(result.message || 'Action completed successfully!')
          }
        }
        
        // If it's a quiz suggestion, navigate to quiz
        if (action.type === 'suggest_retake_quiz' && result.data?.navigate_to_quiz) {
          onStartQuiz()
        }
      } else {
        console.error(result.message || 'Failed to execute action. Please try again.')
        // On non-conflict error, clear loading states but keep picker open for calendar actions
        setExecutingAction(null)
        setSelectingTime(false)
        setSelectedTimeValue(null)
        // Don't close picker on error - let user try again
      }
    } catch (error) {
      console.error('Error executing action:', error)
      console.error('Failed to execute action. Please try again.')
      // On error, clear loading states but keep picker open for calendar actions
      setExecutingAction(null)
      setSelectingTime(false)
      setSelectedTimeValue(null)
      // Don't close picker on error - let user try again
    } finally {
      // Clear loading state only if we didn't return early (conflict case)
      // The conflict case returns early, so this won't run for conflicts
      // For successful actions, we've already handled closing the picker above
      // For errors, we want to keep the picker open
      // This is just a safety net to ensure loading states are cleared
    }
  }

  const handleTimeSelection = (selectedTime) => {
    if (pendingCalendarAction && !selectingTime) {
      console.log('[Time Selection] User selected time:', {
        selectedTime,
        original_time_window: pendingCalendarAction.params?.time_window,
        action_purpose: pendingCalendarAction.params?.purpose,
        duration_minutes: pendingCalendarAction.params?.duration_minutes
      })
      
      // Clear any previous conflict error
      setConflictError(null)
      // Store the selected time value for display
      setSelectedTimeValue(selectedTime)
      // Set loading state
      setSelectingTime(true)
      // Ensure time picker stays open during processing
      // Don't allow overlay clicks to close it while processing
      
      // If selectedTime is a datetime-local value (YYYY-MM-DDTHH:MM format),
      // append the user's timezone offset to help the backend interpret it correctly
      let timeToSend = selectedTime
      if (selectedTime && selectedTime.includes('T') && selectedTime.length === 16) {
        // Get user's timezone offset
        const now = new Date()
        const tzOffset = -now.getTimezoneOffset() // in minutes
        const tzHours = Math.floor(Math.abs(tzOffset) / 60)
        const tzMinutes = Math.abs(tzOffset) % 60
        const tzSign = tzOffset >= 0 ? '+' : '-'
        const tzString = `${tzSign}${tzHours.toString().padStart(2, '0')}:${tzMinutes.toString().padStart(2, '0')}`
        // Also send timezone name if available
        try {
          const tzName = Intl.DateTimeFormat().resolvedOptions().timeZone
          timeToSend = `${selectedTime}${tzString}|${tzName}`
          console.log(`[Time Selection] Added timezone info: ${tzString}|${tzName}`)
        } catch (e) {
          timeToSend = `${selectedTime}${tzString}`
          console.log(`[Time Selection] Added timezone offset: ${tzString}`)
        }
      }
      
      console.log(`[Time Selection] Sending time to backend: ${timeToSend}`)
      
      // Check if this is from toolkit (has source in params or message contains "Schedule time for:")
      const isFromToolkit = pendingCalendarAction.params?.source === 'toolkit' || 
                           pendingCalendarAction.message?.includes('Schedule time for:')
      
      if (isFromToolkit) {
        console.log('[Time Selection] Routing to toolkit handler')
        handleConfirmCalendarFromToolkit(pendingCalendarAction, timeToSend)
      } else {
        console.log('[Time Selection] Routing to regular action handler')
        handleConfirmAction(pendingCalendarAction, timeToSend)
      }
    }
  }

  const formatFreeSlotTime = (isoString) => {
    if (!isoString) return 'No time set'
    
    // Parse the ISO string and convert to Pacific time
    const date = new Date(isoString)
    
    // Convert to Pacific timezone for display
    const pacificDate = new Date(date.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }))
    const now = new Date()
    const nowPacific = new Date(now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }))
    
    // Check if it's today in Pacific time
    const isToday = pacificDate.toDateString() === nowPacific.toDateString()
    
    // Check if the time is in the past (in Pacific time)
    if (date < now) {
      console.warn(`[formatFreeSlotTime] WARNING: Time ${isoString} is in the past! Current time: ${now.toISOString()}`)
    }
    
    // Format in Pacific timezone
    const options = { 
      timeZone: 'America/Los_Angeles',
      hour: 'numeric', 
      minute: '2-digit', 
      hour12: true 
    }
    
    if (isToday) {
      return `Today at ${date.toLocaleTimeString('en-US', options)} PST`
    } else {
      return date.toLocaleString('en-US', { 
        timeZone: 'America/Los_Angeles',
        weekday: 'short', 
        month: 'short', 
        day: 'numeric',
        hour: 'numeric', 
        minute: '2-digit', 
        hour12: true 
      }) + ' PST'
    }
  }

  const handleDismissAction = async (action) => {
    // Record dismissed action
    if (userId) {
      try {
        await recordAction(
          userId,
          action.type,
          action.message,
          'dismissed',
          action.params
        )
        // Refresh user memory to update statistics
        fetchUserMemory()
      } catch (error) {
        // Log error but don't break the user experience
        // This is a non-critical operation
        console.error('Error recording dismissed action (non-critical):', error)
        if (error.code === 'permission-denied') {
          console.warn('Firestore permission denied. Please add security rules for agent_history collection. See FIRESTORE_RULES_AGENT_HISTORY.md')
        }
      }
    }
    
    // Remove the suggestion from the list and fetch a replacement
    setAgentSuggestions(prev => prev.filter(a => a !== action))
    
    // Fetch a new suggestion to replace the one that was dismissed
    // Use a short delay to allow state to update
    setTimeout(() => {
      fetchAgentSuggestions(false) // false = append, don't replace all
    }, 500)
  }

  // Handle scheduling calendar time for a toolkit item
  const handleScheduleFromToolkit = async (item) => {
    const recommendation = item.recommendation || item
    const title = recommendation.title || 'Self-care activity'
    const timeEstimate = recommendation.time_estimate || recommendation.timeEstimate || '30 minutes'
    
    // Extract duration from time estimate (e.g., "30 minutes" -> 30)
    const durationMatch = timeEstimate.match(/(\d+)/)
    const durationMinutes = durationMatch ? parseInt(durationMatch[1]) : 30
    
    console.log(`[Toolkit Schedule] Creating calendar action for: ${title}, duration: ${durationMinutes} minutes`)
    
    // Create action WITHOUT time_window - we'll fetch free slots and set it
    const action = {
      type: 'create_calendar_block',
      message: `Schedule time for: ${title}`,
      requires_confirmation: true,
      params: {
        duration_minutes: durationMinutes,
        // Don't set time_window - will be set from free slots
        purpose: title,
        source: 'toolkit',
        toolkit_item_id: item.id,
        toolkit_item_title: title
      }
    }
    
    console.log(`[Toolkit Schedule] Action created (no time_window):`, action)
    
    // Show time picker and fetch free slots to find the best suggested time
    setPendingCalendarAction(action)
    setShowTimePicker(true)
    
    // Fetch free slots for this duration to find the best suggested time
    // Pass the action directly to avoid closure issues
    await fetchFreeSlots(durationMinutes, action)
  }

  // Handle creating journal entry for a toolkit item
  const handleJournalFromToolkit = async (item) => {
    const recommendation = item.recommendation || item
    const title = recommendation.title || 'Self-care activity'
    const whyItHelps = recommendation.why_it_helps || recommendation.whyItHelps || ''
    const steps = recommendation.steps || []
    
    // Create a personalized journal prompt based on the recommendation
    const promptTemplate = `Reflecting on: ${title}

${whyItHelps ? `Why this helps: ${whyItHelps}` : ''}

${steps.length > 0 ? `Steps to try:\n${steps.map((step, idx) => `${idx + 1}. ${step}`).join('\n')}` : ''}

How do you feel about trying this activity? What might get in the way? What would make it easier to start?`

    const action = {
      type: 'create_journal_entry',
      message: `Start a journal entry about: ${title}`,
      requires_confirmation: true,
      params: {
        prompt_template: promptTemplate,
        toolkit_item_id: item.id, // Add item ID to track which item is being processed
        toolkit_item_title: title
      }
    }

    try {
      setExecutingAction(action) // Track the specific action
      const result = await onExecuteAction(action, userId)
      
      if (result.success) {
        // Record the action in user memory with toolkit context
        if (userId) {
          try {
            const actionId = await recordAction(
              userId,
              'create_journal_entry',
              `Created journal entry from toolkit item: ${title}`,
              'confirmed',
              {
                ...action.params,
                toolkit_item_id: item.id,
                toolkit_item_title: title,
                source: 'toolkit'
              }
            )
            // Refresh user memory to update statistics
            fetchUserMemory()
            console.log(`Journal entry created from toolkit item: ${title}`)
          } catch (error) {
            // Log error but don't break the user experience
            // This is a non-critical operation - the journal entry was still created
            console.error('Error recording toolkit action (non-critical):', error)
            if (error.code === 'permission-denied') {
              console.warn('Firestore permission denied. Please add security rules for agent_history collection. See FIRESTORE_RULES_AGENT_HISTORY.md')
            }
          }
        }
        
        // If there's a document URL, open it in a new tab
        if (result.data?.document_url) {
          window.open(result.data.document_url, '_blank')
          // Refresh journal entries after a short delay
          setTimeout(() => {
            fetchJournalEntries()
          }, 2000)
        }
      } else {
        console.error(result.message || 'Failed to create journal entry.')
      }
    } catch (error) {
      console.error('Error creating journal entry from toolkit:', error)
    } finally {
      setExecutingAction(null)
    }
  }

  // Handle confirming calendar action from toolkit (after time selection)
  const handleConfirmCalendarFromToolkit = async (action, customTime = null) => {
    try {
      setExecutingAction(action) // Track the specific action
      
      // Update action params if custom time is provided
      const actionToExecute = customTime
        ? {
            ...action,
            params: {
              ...action.params,
              time_window: customTime
            }
          }
        : action

      const result = await onExecuteAction(actionToExecute, userId)
      
      // Check for conflict error FIRST - before any other handling
      if (!result.success && result.conflict) {
        // Conflict detected - show error and keep time picker open
        console.log('CONFLICT DETECTED in toolkit handler - Result:', result)
        console.log('CONFLICT MESSAGE:', result.message)
        const errorMessage = result.message || 'This time conflicts with an existing event. Please choose another time.'
        console.log('Setting conflict error:', errorMessage)
        setConflictError(errorMessage)
        setExecutingAction(null) // Clear loading state
        setSelectingTime(false) // Clear time selection loading
        setSelectedTimeValue(null) // Clear selected time
        // IMPORTANT: Ensure time picker stays open
        // Explicitly keep these states set to keep modal visible
        if (!showTimePicker) {
          console.warn('Time picker was closed, reopening it for conflict display')
          setShowTimePicker(true)
        }
        if (!pendingCalendarAction) {
          console.warn('Pending calendar action was cleared, restoring it for conflict display')
          setPendingCalendarAction(action)
        }
        // Keep time picker open so user can select another time
        // Don't close the time picker or clear pendingCalendarAction
        return // Exit early - don't run finally block logic that might close picker
      }
      
      if (result.success) {
        // Extract toolkit item info from action message or params
        const toolkitTitle = action.params?.purpose || action.message.replace('Schedule time for: ', '')
        
        // Record the action in user memory with toolkit context
        if (userId) {
          try {
            const actionId = await recordAction(
              userId,
              'create_calendar_block',
              `Scheduled calendar time from toolkit item: ${toolkitTitle}`,
              'confirmed',
              {
                ...actionToExecute.params,
                source: 'toolkit'
              }
            )
            // Refresh user memory to update statistics
            fetchUserMemory()
            console.log(`Calendar event created from toolkit item: ${toolkitTitle}`)
          } catch (error) {
            // Log error but don't break the user experience
            // This is a non-critical operation - the calendar event was still created
            console.error('Error recording toolkit action (non-critical):', error)
            if (error.code === 'permission-denied') {
              console.warn('Firestore permission denied. Please add security rules for agent_history collection. See FIRESTORE_RULES_AGENT_HISTORY.md')
            }
          }
        }
        
        // If there's an HTML link, open it in a new tab
        if (result.data?.html_link) {
          window.open(result.data.html_link, '_blank')
          // Clear the datetime input for next time
          setCustomDateTime('')
          // Close the time picker modal and clear loading states
          setShowTimePicker(false)
          setPendingCalendarAction(null)
          setSelectingTime(false)
          setSelectedTimeValue(null)
          setFreeSlots([])
          setConflictError(null)
          // Refresh calendar events after a short delay
          setTimeout(() => {
            fetchCalendarEvents()
          }, 2000)
        }
      } else {
        // Non-conflict error - show message but keep picker open
        setConflictError(result.message || 'Failed to create calendar event. Please try again.')
        setExecutingAction(null)
        setSelectingTime(false)
        setSelectedTimeValue(null)
        // Don't close picker on error - let user try again
      }
    } catch (error) {
      console.error('Error creating calendar event from toolkit:', error)
      // On error, clear loading states but keep picker open
      setExecutingAction(null)
      setSelectingTime(false)
      setSelectedTimeValue(null)
      setConflictError('An error occurred. Please try again.')
      // Don't close picker on error - let user try again
    } finally {
      // Only clear loading states if we didn't return early (conflict case)
      // The conflict case returns early, so this won't run for conflicts
      // For successful actions, we've already handled closing the picker above
      // For errors, we want to keep the picker open
      // This is just a safety net to ensure loading states are cleared
    }
  }

  const getSuggestedTimeLabel = (timeWindow) => {
    const now = new Date()
    const currentHour = now.getHours()
    const currentMinute = now.getMinutes()
    
    // Check if suggested times have passed and adjust labels accordingly
    const labels = {}
    
    // Today morning (9 AM) - if past, show tomorrow
    if (currentHour < 9 || (currentHour === 9 && currentMinute === 0)) {
      labels['today_morning'] = 'Today at 9:00 AM'
    } else {
      labels['today_morning'] = 'Tomorrow at 9:00 AM'
    }
    
    // Today afternoon (2 PM) - if past, show tomorrow
    if (currentHour < 14 || (currentHour === 14 && currentMinute === 0)) {
      labels['today_afternoon'] = 'Today at 2:00 PM'
    } else {
      labels['today_afternoon'] = 'Tomorrow at 2:00 PM'
    }
    
    // Today evening (7 PM) - if past, show tomorrow
    if (currentHour < 19 || (currentHour === 19 && currentMinute === 0)) {
      labels['today_evening'] = 'Today at 7:00 PM'
    } else {
      labels['today_evening'] = 'Tomorrow at 7:00 PM'
    }
    
    labels['tomorrow_morning'] = 'Tomorrow at 9:00 AM'
    labels['tomorrow_afternoon'] = 'Tomorrow at 2:00 PM'
    
    return labels[timeWindow] || timeWindow
  }

  const getSelectedTimeLabel = (timeValue) => {
    if (!timeValue) return ''
    
    // Handle relative time strings
    const timeLabels = {
      'now': 'Now',
      'in_1_hour': 'In 1 hour',
      'in_2_hours': 'In 2 hours',
      'tomorrow_morning': 'Tomorrow at 9:00 AM',
      'tomorrow_afternoon': 'Tomorrow at 2:00 PM',
      'today_morning': 'Today at 9:00 AM',
      'today_afternoon': 'Today at 2:00 PM',
      'today_evening': 'Today at 7:00 PM'
    }
    
    if (timeLabels[timeValue]) {
      return timeLabels[timeValue]
    }
    
    // Handle ISO datetime strings (from datetime-local input)
    try {
      const date = new Date(timeValue)
      if (!isNaN(date.getTime())) {
        // Format as readable date and time
        const options = { 
          weekday: 'short', 
          month: 'short', 
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          hour12: true
        }
        return date.toLocaleString('en-US', options)
      }
    } catch (e) {
      // If parsing fails, return the value as-is
    }
    
    return timeValue
  }

  return (
    <div className="quiz-page active dashboard-page">
      <div className="dashboard-header">
        <h1>Welcome back{userName ? `, ${userName}` : ''}</h1>
      </div>
      
      {!showToolkit && !showToolkitOnly ? (
        <div className="dashboard-content">
          {/* Left Column */}
          <div className="dashboard-left-column">
            {/* Support Container */}
            <div className="dashboard-section support-section">
              <h3 className="section-title">How can we support you today?</h3>
              <button className="primary-button take-quiz-button" onClick={onStartQuiz}>
                Take the Quiz
              </button>
            </div>

            {/* Upcoming Events Container */}
            <div className="dashboard-section upcoming-events-section">
              <h3 className="section-title">Upcoming Events</h3>
              {loadingEvents ? (
                <div className="loading-text">Loading events...</div>
              ) : calendarEvents.length === 0 ? (
                <div className="empty-message">No upcoming events scheduled</div>
              ) : (
                <div className="events-list">
                  {calendarEvents.map((event, index) => {
                    const startDate = new Date(event.start)
                    const formattedDate = startDate.toLocaleDateString('en-US', {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                      hour12: true
                    })
                    return (
                      <div key={event.id || index} className="event-item">
                        <div className="event-content">
                          <h4 className="event-title">{event.title}</h4>
                          <p className="event-time">{formattedDate}</p>
                        </div>
                        {event.html_link && (
                          <a 
                            href={event.html_link} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="event-link"
                          >
                            View in Calendar →
                          </a>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Recent Journal Entries Container */}
            <div className="dashboard-section journal-entries-section">
              <h3 className="section-title">Recent Journal Entries</h3>
              {loadingJournals ? (
                <div className="loading-text">Loading entries...</div>
              ) : journalEntries.length === 0 ? (
                <div className="empty-message">No journal entries yet</div>
              ) : (
                <div className="journal-list">
                  {journalEntries.map((entry, index) => {
                    const createdDate = new Date(entry.created_time)
                    const formattedDate = createdDate.toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric'
                    })
                    return (
                      <div key={entry.id || index} className="journal-item">
                        <div className="journal-content">
                          <h4 className="journal-title">{entry.title}</h4>
                          <p className="journal-date">{formattedDate}</p>
                        </div>
                        {entry.document_url && (
                          <a 
                            href={entry.document_url} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="journal-link"
                          >
                            Open →
                          </a>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right Column */}
          <div className="dashboard-right-column">
            {/* Agent Suggestions Container */}
            <div className="dashboard-section agent-suggestions-section">
              {loadingSuggestions ? (
                <div className="loading-text">Loading suggestions...</div>
              ) : (
                <>
                  <h3 className="section-title">Agent Suggestions</h3>
                  {agentSuggestions.length > 0 ? (
                    <div className="suggestions-container">
                      {agentSuggestions.map((action, index) => {
                        // Check if this specific action is being executed (compare by reference or unique properties)
                        const isExecuting = executingAction && 
                          executingAction.type === action.type && 
                          executingAction.message === action.message &&
                          JSON.stringify(executingAction.params) === JSON.stringify(action.params)
                        return (
                          <div key={index} className="suggestion-card">
                            <p className="suggestion-message">{action.message}</p>
                            {isExecuting ? (
                              <div className="action-loading">
                                <div className="loading-spinner"></div>
                                <p>Processing your request...</p>
                              </div>
                            ) : (
                              <div className="suggestion-actions">
                                <button 
                                  className="confirm-button"
                                  onClick={() => handleConfirmAction(action)}
                                >
                                  Confirm
                                </button>
                                <button 
                                  className="dismiss-button"
                                  onClick={() => handleDismissAction(action)}
                                >
                                  Dismiss
        </button>
      </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="loading-text">Loading suggestions...</div>
                  )}
                </>
              )}
            </div>

            {/* Toolkit Container */}
            <div className="dashboard-section toolkit-section">
              <h3 className="section-title">My Toolkit</h3>
              {loading ? (
                <div className="loading-text">Loading your toolkit...</div>
              ) : toolkitItems.length === 0 ? (
                <div className="empty-toolkit-preview">
                  <p className="empty-message">Your toolkit is empty. Save recommendations from quiz results to build your toolkit!</p>
                </div>
              ) : (
                <>
                  <div className="toolkit-grid">
                    {toolkitItems.slice(0, 4).map((item) => {
                      const recommendation = item.recommendation || item
                      const title = recommendation.title || 'Untitled'
                      const timeEstimate = recommendation.time_estimate || ''
                      const difficulty = recommendation.difficulty || ''
                      return (
                        <div key={item.id} className="toolkit-item">
                          <div className="toolkit-item-content">
                            <h4 className="toolkit-item-title">{title}</h4>
                            {(timeEstimate || difficulty) && (
                              <p className="toolkit-item-meta">
                                {timeEstimate && <span>⏱️ {timeEstimate}</span>}
                                {difficulty && <span>📊 {difficulty}</span>}
                              </p>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  {toolkitItems.length > 0 && (
                    <button 
                      className="view-all-button" 
                      onClick={() => onViewToolkit && onViewToolkit()}
                    >
                      View All ({toolkitItems.length} {toolkitItems.length === 1 ? 'item' : 'items'})
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Disclaimer Container - spans full width */}
          <div className="dashboard-section disclaimer-section disclaimer-full-width">
            <p className="disclaimer-text">
              This is general wellness guidance, not medical advice. If you're in crisis, contact campus counseling or emergency services.
            </p>
          </div>
        </div>
      ) : (
        <div className="toolkit-view">
          <div className="toolkit-header">
            <h2>My Toolkit</h2>
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
            <div className="toolkit-items">
              {toolkitItems.map((item) => {
                // Handle both nested recommendation structure and flat structure
                const recommendation = item.recommendation || item
                const title = recommendation.title || 'Untitled'
                const whyItHelps = recommendation.why_it_helps || recommendation.whyItHelps || ''
                const steps = recommendation.steps || []
                const timeEstimate = recommendation.time_estimate || recommendation.timeEstimate || ''
                const difficulty = recommendation.difficulty || ''
                
                return (
                  <div key={item.id} className="toolkit-item-card">
                    <h4>{title}</h4>
                    {whyItHelps && (
                      <p className="toolkit-item-why">{whyItHelps}</p>
                    )}
                    {steps && steps.length > 0 && (
                      <div className="toolkit-item-steps">
                        <strong>Steps:</strong>
                        <ol>
                          {steps.map((step, idx) => (
                            <li key={idx}>{step}</li>
                          ))}
                        </ol>
                      </div>
                    )}
                    <div className="toolkit-item-meta">
                      {timeEstimate && <span>⏱️ {timeEstimate}</span>}
                      {difficulty && <span>📊 {difficulty}</span>}
                    </div>
                    <div className="toolkit-item-actions">
                      <button 
                        className="toolkit-action-button schedule-button"
                        onClick={() => handleScheduleFromToolkit(item)}
                      >
                        📅 Schedule Time
                      </button>
                      <button 
                        className="toolkit-action-button journal-button"
                        onClick={() => handleJournalFromToolkit(item)}
                        disabled={executingAction && executingAction.type === 'create_journal_entry' && executingAction.params?.toolkit_item_id === item.id}
                      >
                        {executingAction && executingAction.type === 'create_journal_entry' && executingAction.params?.toolkit_item_id === item.id ? (
                          <>
                            <div className="loading-spinner-small"></div>
                            Creating Journal Entry...
                          </>
                        ) : (
                          '✍️ Start Journal Entry'
                        )}
                      </button>
                      <button 
                        className="delete-toolkit-button"
                        onClick={() => handleDeleteToolkitItem(item.id)}
                      >
                        Remove from Toolkit
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Time Picker Modal - Always available when needed */}
      {showTimePicker && pendingCalendarAction && (
            <div className="time-picker-overlay" onClick={() => { if (!selectingTime) { setShowTimePicker(false); setPendingCalendarAction(null); setCustomDateTime(''); setFreeSlots([]); setConflictError(null); } }}>
              <div className="time-picker-modal" onClick={(e) => e.stopPropagation()}>
                <h3>Choose when to schedule this</h3>
                <p className="time-picker-description">
                  {pendingCalendarAction.params.purpose}
                </p>
                {loadingFreeSlots && (
                  <p className="loading-free-slots">Checking your calendar for free times...</p>
                )}
                
                {conflictError && (
                  <div className="conflict-error-message">
                    <div className="conflict-error-content">
                      <p className="conflict-error-title">⚠️ Conflict Detected</p>
                      <p className="conflict-error-text">{conflictError}</p>
                    </div>
                    <button 
                      className="conflict-dismiss-button"
                      onClick={() => setConflictError(null)}
                    >
                      Dismiss
                    </button>
                  </div>
                )}
                
                {selectingTime ? (
                  <div className="time-picker-loading">
                    <div className="loading-spinner"></div>
                    <p>Creating calendar event for {getSelectedTimeLabel(selectedTimeValue)}...</p>
                  </div>
                ) : (
                  <>
                    {/* Main suggested time - check if it's an ISO datetime (from free slots) */}
                    {(() => {
                      const timeWindow = pendingCalendarAction.params.time_window
                      const isISO = timeWindow && timeWindow.includes('T') && timeWindow.length > 16
                      
                      console.log('[Time Picker] Rendering suggested time:', {
                        time_window: timeWindow,
                        time_window_type: timeWindow ? (isISO ? 'ISO_DATETIME' : 'RELATIVE') : 'NOT_SET',
                        isISO: isISO,
                        purpose: pendingCalendarAction.params?.purpose,
                        duration: pendingCalendarAction.params?.duration_minutes,
                        free_slots_count: freeSlots.length,
                        full_params: JSON.stringify(pendingCalendarAction.params)
                      })
                      
                      if (timeWindow && !isISO) {
                        console.error(`[Time Picker] ⚠️ ERROR: Rendering RELATIVE time_window "${timeWindow}" - backend should have converted this to ISO datetime!`)
                      }
                      
                      if (timeWindow) {
                        if (isISO) {
                          // This is an ISO datetime from free slots
                          return (
                            <div className="main-suggested-time">
                              <label>✨ Suggested time (based on your calendar):</label>
                              <button 
                                className="time-option-button main-suggested"
                                onClick={() => handleTimeSelection(pendingCalendarAction.params.time_window)}
                                disabled={selectingTime}
                              >
                                {formatFreeSlotTime(pendingCalendarAction.params.time_window)}
                              </button>
                              <p className="suggested-time-note">This time is free in your calendar</p>
                            </div>
                          )
                        } else {
                          // This is a relative time like "today_afternoon"
                          return (
                            <div className="main-suggested-time">
                              <label>✨ Suggested time:</label>
                              <button 
                                className="time-option-button main-suggested"
                                onClick={() => handleTimeSelection(pendingCalendarAction.params.time_window)}
                                disabled={selectingTime}
                              >
                                {getSuggestedTimeLabel(pendingCalendarAction.params.time_window)}
                              </button>
                            </div>
                          )
                        }
                      } else {
                        // No time_window set - should not happen, but show a message
                        console.warn('[Time Picker] No time_window set in pendingCalendarAction.params')
                        return (
                          <div className="main-suggested-time">
                            <label>✨ Suggested time:</label>
                            <p className="suggested-time-note">Please select a time below</p>
                          </div>
                        )
                      }
                    })()}
                    
                    <div className="time-options">
                      <label>Or choose another time:</label>
                      <button 
                        className="time-option-button"
                        onClick={() => handleTimeSelection('now')}
                        disabled={selectingTime}
                      >
                        Now
                      </button>
                      <button 
                        className="time-option-button"
                        onClick={() => handleTimeSelection('in_1_hour')}
                        disabled={selectingTime}
                      >
                        In 1 hour
                      </button>
                    </div>
                    
                    <div className="time-picker-custom">
                      <label>Or choose a specific date and time:</label>
                      <input 
                        type="datetime-local" 
                        className="datetime-input"
                        min={new Date().toISOString().slice(0, 16)}
                        value={customDateTime}
                        disabled={selectingTime}
                        onChange={(e) => {
                          setCustomDateTime(e.target.value)
                        }}
                      />
                      {customDateTime && (
                        <button
                          className="time-option-button"
                          onClick={() => handleTimeSelection(customDateTime)}
                          disabled={selectingTime}
                        >
                          Schedule for {new Date(customDateTime).toLocaleString('en-US', { 
                            month: 'short', 
                            day: 'numeric',
                            hour: 'numeric', 
                            minute: '2-digit', 
                            hour12: true 
                          })}
                        </button>
                      )}
                    </div>
                    
                    <button 
                      className="time-picker-cancel"
                      onClick={() => { 
                        setShowTimePicker(false); 
                        setPendingCalendarAction(null); 
                        setCustomDateTime(''); 
                        setFreeSlots([]); 
                        setConflictError(null); 
                      }}
                      disabled={selectingTime}
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

      {/* Feedback Modal */}
      {showFeedback && pendingFeedbackActionId && (
        <div className="feedback-overlay" onClick={() => { setShowFeedback(false); setPendingFeedbackActionId(null); }}>
          <div className="feedback-modal" onClick={(e) => e.stopPropagation()}>
            <ActionFeedback
              actionId={pendingFeedbackActionId}
              onClose={() => {
                setShowFeedback(false)
                setPendingFeedbackActionId(null)
                // Refresh user memory after feedback
                fetchUserMemory()
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default Dashboard

