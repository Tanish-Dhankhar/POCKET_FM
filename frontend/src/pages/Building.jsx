import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as flow from '../api/flow'
import * as studio from '../api/studio'
import AILoadingScreen from '../components/AILoadingScreen'
import { useWizard } from '../store/wizard'

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export default function Building() {
  const { seriesId, confirm } = useWizard()
  const navigate = useNavigate()
  const started = useRef(false)
  const [error, setError] = useState('')

  async function build() {
    setError('')
    try {
      await flow.buildSeries(seriesId, confirm)
      const queued = await studio.regenerateAnalysis(seriesId)
      while (true) {
        const job = await studio.getJob(queued.id)
        if (job.state === 'error') throw new Error(job.error || 'Story analysis failed.')
        if (job.state === 'done') break
        await wait(1000)
      }
      navigate(`/series/${seriesId}`, { replace: true })
    } catch (e) { setError(e.message); started.current = false }
  }

  useEffect(() => {
    if (seriesId && confirm && !started.current) { started.current = true; build() }
  }, [seriesId]) // eslint-disable-line react-hooks/exhaustive-deps

  const expired = !seriesId || !confirm

  return (
    <div className="fixed inset-0 z-[150]">
      <AILoadingScreen />
      {(error || expired) && (
        <div className="absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-3 text-center">
          <p className="error text-sm px-4">
            {expired ? 'This build session expired. Your saved series is still available on the dashboard.' : error}
          </p>
          <div className="flex gap-3">
            <button className="button ghost" onClick={() => navigate('/')}>Back</button>
            {!expired && error && (
              <button className="button primary" onClick={() => { if (!started.current) { started.current = true; build() } }}>Try again</button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
