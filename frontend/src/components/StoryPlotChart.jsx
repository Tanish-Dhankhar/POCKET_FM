import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

function PlotTooltip({ active, payload }) {
  const point = active && payload?.[0]?.payload
  if (!point) return null

  return <div className="story-plot-tooltip">
    <strong>{point.order}. {point.label}</strong>
    <span>{point.intensity}% intensity · line {point.line_index + 1}</span>
    <p>{point.description}</p>
  </div>
}

function PlotDot({ cx, cy, payload }) {
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null
  return <g className="story-plot-dot">
    <circle cx={cx} cy={cy} r="9" />
    <text x={cx} y={cy} dy="0.35em" textAnchor="middle">{payload.order}</text>
  </g>
}

export default function StoryPlotChart({ plot, lineCount, stale = false }) {
  const points = useMemo(() => {
    const lastLine = Math.max(1, lineCount - 1)
    return (plot?.points || []).map((point, index) => ({
      ...point,
      order: index + 1,
      progress: Math.max(0, Math.min(100, (Number(point.line_index) / lastLine) * 100)),
    }))
  }, [plot?.points, lineCount])

  if (!points.length) return <section className="story-plot-card story-plot-empty">
    <p className="card-label">Story plot</p>
    <div className="story-plot-placeholder" aria-hidden="true"><i /><i /><i /><i /><i /></div>
    <p>{lineCount
      ? 'Refresh the editorial review to map this existing script.'
      : 'The story curve will appear automatically when the script is generated.'}</p>
  </section>

  return <section className="story-plot-card">
    <div className="story-plot-head">
      <div>
        <p className="card-label">Story plot</p>
        <span>{plot.structure || 'Dramatic structure'}</span>
      </div>
      <em>Script derived</em>
    </div>
    {stale && <p className="stale-note">This curve refers to an earlier script version.</p>}
    <div className="story-plot-chart" role="img" aria-label={`Story intensity curve with ${points.length} beats`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 16, right: 11, bottom: 2, left: 11 }}>
          <defs>
            <linearGradient id="episode-story-plot" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#E61C38" stopOpacity="0.48" />
              <stop offset="100%" stopColor="#E61C38" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#242424" strokeDasharray="3 5" vertical={false} />
          <XAxis dataKey="progress" type="number" domain={[0, 100]} hide />
          <YAxis domain={[0, 100]} hide />
          <Tooltip content={<PlotTooltip />} cursor={{ stroke: '#555', strokeDasharray: '3 3' }} />
          <Area
            type="monotoneX"
            dataKey="intensity"
            stroke="#E61C38"
            strokeWidth={2.5}
            fill="url(#episode-story-plot)"
            dot={<PlotDot />}
            activeDot={{ r: 5, fill: '#fff', stroke: '#E61C38', strokeWidth: 3 }}
            isAnimationActive
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
    <div className="story-plot-axis"><span>Opening</span><span>Episode progress</span><span>Ending</span></div>
    {plot.summary && <p className="story-plot-summary">{plot.summary}</p>}
    <ol className="story-plot-legend">
      {points.map((point) => <li key={`${point.line_index}-${point.order}`} title={point.description}>
        <i>{point.order}</i><span>{point.label}</span>
      </li>)}
    </ol>
  </section>
}
