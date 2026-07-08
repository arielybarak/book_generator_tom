export function Card({ className = '', ...props }) {
  return (
    <div
      className={`rounded-card border-line bg-surface shadow-card border ${className}`}
      {...props}
    />
  )
}
