/**
 * LoadingIcons.jsx
 * Mathematically precise, hand-drawn inline SVGs for <AILoadingScreen />.
 * No external icon libraries — pure SVG primitives.
 *
 * Global style contract (applied on every <svg>):
 *   fill           #1E1E24  (dark slate/charcoal)
 *   stroke         #E61C38  (vivid crimson)
 *   strokeWidth    2        (overridden per-element where the spec notes it)
 *   strokeLinejoin round
 *   strokeLinecap  round
 */

const base = {
  fill: '#1E1E24',
  stroke: '#E61C38',
  strokeWidth: 2,
  strokeLinejoin: 'round',
  strokeLinecap: 'round',
}

/* 1. Open Carton (isometric box) — the central hopper */
export const Box = ({ className = '' }) => (
  <svg viewBox="0 0 200 200" className={className} {...base}>
    {/* Back flaps (drawn first, behind everything) */}
    <polygon points="30,70 10,30 80,0 100,30" />
    <polygon points="170,70 190,30 120,0 100,30" />
    {/* Inside back / depth (darker fill, red stroke) */}
    <polygon points="30,70 100,30 170,70 100,110" fill="#121215" />
    {/* Front faces */}
    <polygon points="100,180 30,140 30,70 100,110" />
    <polygon points="100,180 170,140 170,70 100,110" />
    {/* Front flaps (drawn last, in front) */}
    <polygon points="30,70 100,110 80,150 10,110" />
    <polygon points="100,110 170,70 190,110 120,150" />
  </svg>
)

/* 2. Basketball */
export const Basketball = ({ className = '' }) => (
  <svg viewBox="0 0 100 100" className={className} {...base}>
    <circle cx="50" cy="50" r="45" />
    <path d="M 50 5 L 50 95" fill="none" />
    <path d="M 5 50 L 95 50" fill="none" />
    <path d="M 25 10 A 35 35 0 0 1 25 90" fill="none" />
    <path d="M 75 10 A 35 35 0 0 0 75 90" fill="none" />
  </svg>
)

/* 3. Potted Plant (aloe / succulent) */
export const Plant = ({ className = '' }) => (
  <svg viewBox="0 0 100 100" className={className} {...base}>
    {/* Leaves first, so the pot overlaps their bases */}
    <path d="M 45 55 Q 50 10 50 5 Q 50 10 55 55 Z" />
    <path d="M 40 55 Q 20 30 10 20 Q 25 35 45 55 Z" />
    <path d="M 60 55 Q 80 30 90 20 Q 75 35 55 55 Z" />
    {/* Pot */}
    <polygon points="30,95 70,95 80,65 20,65" />
    <rect x="15" y="55" width="70" height="10" rx="3" />
  </svg>
)

/* 4. Desk Lamp */
export const Lamp = ({ className = '' }) => (
  <svg viewBox="0 0 100 100" className={className} {...base}>
    {/* Light beam (behind, semi-transparent, no stroke) */}
    <polygon
      points="10,15 5,40 -20,10 -20,60"
      fill="rgba(230, 28, 56, 0.2)"
      stroke="none"
    />
    <ellipse cx="80" cy="90" rx="15" ry="5" />
    <line x1="80" y1="90" x2="60" y2="50" strokeWidth={4} />
    <line x1="60" y1="50" x2="30" y2="30" strokeWidth={4} />
    <circle cx="60" cy="50" r="4" />
    {/* Lamp head cone */}
    <polygon points="30,30 10,15 5,40" />
  </svg>
)

/* 5. Stack of Pillows */
export const Pillows = ({ className = '' }) => (
  <svg viewBox="0 0 100 100" className={className} {...base}>
    <path d="M 10 75 C 10 60, 90 60, 90 75 C 90 90, 10 90, 10 75 Z" />
    <path d="M 15 60 C 15 45, 85 45, 85 60 C 85 75, 15 75, 15 60 Z" />
    <path d="M 20 45 C 20 30, 80 30, 80 45 C 80 60, 20 60, 20 45 Z" />
  </svg>
)

/* 6. Folded Blanket */
export const Blanket = ({ className = '' }) => (
  <svg viewBox="0 0 100 100" className={className} {...base}>
    <rect x="10" y="40" width="80" height="50" rx="10" />
    <line x1="10" y1="65" x2="90" y2="65" />
    {/* Woven texture — dashed parallel lines across the top half */}
    <line x1="20" y1="47" x2="80" y2="47" strokeDasharray="4 2" fill="none" />
    <line x1="20" y1="51" x2="80" y2="51" strokeDasharray="4 2" fill="none" />
    <line x1="20" y1="55" x2="80" y2="55" strokeDasharray="4 2" fill="none" />
    <line x1="20" y1="59" x2="80" y2="59" strokeDasharray="4 2" fill="none" />
  </svg>
)

/* 7. Minimalist Bicycle */
export const Bicycle = ({ className = '' }) => (
  <svg viewBox="0 0 100 100" className={className} {...base}>
    {/* Wheels (hollow rings) */}
    <circle cx="25" cy="75" r="20" fill="none" />
    <circle cx="75" cy="75" r="20" fill="none" />
    {/* Glowing hubs */}
    <circle cx="25" cy="75" r="4" fill="#E61C38" />
    <circle cx="75" cy="75" r="4" fill="#E61C38" />
    {/* Diamond frame */}
    <polyline points="25,75 40,45 70,45 50,75 25,75" fill="none" strokeWidth={3} />
    {/* Front fork */}
    <line x1="75" y1="75" x2="65" y2="30" strokeWidth={3} />
    {/* Seat post + seat */}
    <line x1="40" y1="45" x2="35" y2="25" strokeWidth={3} />
    <path d="M 25 25 L 45 25 Q 50 25 50 30 L 25 30 Z" />
    {/* Handlebars */}
    <path d="M 60 30 L 75 30 Q 80 30 80 20" fill="none" strokeWidth={3} />
  </svg>
)

// Ordered sequence of falling "ingredients" dropped into the carton.
export const FALLING_ITEMS = [
  { key: 'basketball', label: 'Characters', Icon: Basketball },
  { key: 'plant', label: 'Theme', Icon: Plant },
  { key: 'lamp', label: 'Context', Icon: Lamp },
  { key: 'pillows', label: 'Climax', Icon: Pillows },
  { key: 'blanket', label: 'VFX', Icon: Blanket },
  { key: 'bicycle', label: 'Visuals', Icon: Bicycle },
]
