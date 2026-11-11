const paths = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  generation: <><path d="M12 3v18" /><path d="m7 8 5-5 5 5" /><path d="M5 13v5a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-5" /></>,
  catalog: <><path d="m3 7 9-4 9 4-9 4-9-4Z" /><path d="m3 12 9 4 9-4" /><path d="m3 17 9 4 9-4" /></>,
  recommend: <><path d="m12 3 2.4 5.1L20 9l-4 3.9.9 5.6-4.9-2.7-5 2.7.9-5.6L4 9l5.6-.9L12 3Z" /><path d="m18 16 1.2 2.5L22 19l-2 2 .5 2.8-2.5-1.3-2.5 1.3.5-2.8-2-2 2.8-.5L18 16Z" /></>,
  validation: <><path d="M9 12l2 2 4-4" /><path d="M12 22c4-2 7-5 7-10V5l-7-3-7 3v7c0 5 3 8 7 10Z" /></>,
  evaluation: <><path d="M4 19V5" /><path d="M4 19h17" /><path d="M8 16v-5" /><path d="M13 16V7" /><path d="M18 16v-8" /></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
  refresh: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M5.5 9A7 7 0 0 1 17 6.5L20 12" /><path d="M18.5 15A7 7 0 0 1 7 17.5L4 12" /></>,
  chevron: <path d="m9 18 6-6-6-6" />,
  menu: <><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h16" /></>,
}

export default function Icon({ name, size = 18, className = '' }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] || paths.overview}
    </svg>
  )
}
