// Admin Analytics Tracking System
// Add this to your layout.tsx or as a separate component

'use client'

import { useEffect } from 'react'

export function AnalyticsTracker() {
  useEffect(() => {
    // Track page visit
    const trackVisit = async () => {
      try {
        await fetch('/api/admin/track-visit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            page: window.location.pathname,
            referrer: document.referrer,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),
          })
        })
      } catch (e) {
        // Silent fail for analytics
      }
    }

    // Track errors
    const trackError = async (event: ErrorEvent) => {
      try {
        await fetch('/api/admin/track-error', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: event.message,
            source: event.filename,
            line: event.lineno,
            column: event.colno,
            stack: event.error?.stack,
            page: window.location.pathname,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),
          })
        })
      } catch (e) {
        // Silent fail
      }
    }

    // Track visit on mount
    trackVisit()

    // Listen for errors
    window.addEventListener('error', trackError)

    return () => {
      window.removeEventListener('error', trackError)
    }
  }, [])

  return null
}