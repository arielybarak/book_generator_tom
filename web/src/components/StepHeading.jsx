import { useEffect, useRef } from 'react'

/**
 * Page-step <h1> that takes focus on mount so keyboard and screen-reader users
 * are moved to the new view when the step changes (App swaps step components).
 * tabIndex={-1} makes it programmatically focusable without entering the tab order.
 */
export function StepHeading({ children, className = '' }) {
  const ref = useRef(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  return (
    <h1 ref={ref} tabIndex={-1} className={`outline-none ${className}`}>
      {children}
    </h1>
  )
}
