const SIZES = {
  sm: 'px-4 py-2 text-sm',
  md: 'px-6 py-3 text-base',
  lg: 'px-8 py-4 text-lg',
}

const VARIANTS = {
  primary: 'bg-brand text-white hover:bg-brand-dark shadow-soft',
  accent: 'bg-accent text-white hover:opacity-90 shadow-soft',
  soft: 'bg-brand-soft text-brand-dark hover:bg-brand/15',
  ghost: 'bg-transparent text-ink hover:bg-brand-soft',
}

export function Button({ variant = 'primary', size = 'md', className = '', ...props }) {
  return (
    <button
      className={`rounded-btn inline-flex items-center justify-center gap-2 font-semibold transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${SIZES[size]} ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}
