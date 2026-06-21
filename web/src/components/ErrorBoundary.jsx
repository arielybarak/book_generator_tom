import { Component } from 'react'

/**
 * Top-level safety net: a render error anywhere below shows a friendly Hebrew
 * fallback with a reload button instead of a blank white screen.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled UI error', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-ink text-2xl font-bold">משהו השתבש</h1>
        <p className="text-muted max-w-md">
          קרתה תקלה לא צפויה. אפשר לטעון את העמוד מחדש ולנסות שוב.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="rounded-btn bg-brand shadow-soft hover:bg-brand-dark px-6 py-3 font-semibold text-white transition"
        >
          טעינה מחדש
        </button>
      </div>
    )
  }
}
