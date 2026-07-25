import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as flow from '../api/flow'
import * as studio from '../api/studio'
import GenerationLoader from '../components/GenerationLoader'
import { useWizard } from '../store/wizard'

const wait = (ms) => new Promise((resolve) => setTimeout(resolve,ms))

export default function Building() {
  const {seriesId,confirm} = useWizard()
  const navigate = useNavigate()
  const started = useRef(false)
  const [status,setStatus] = useState({message:'Reading the shape of your story…',progress:8,error:''})

  async function build() {
    setStatus({message:'Writing the series blueprint…',progress:18,error:''})
    try {
      await flow.buildSeries(seriesId,confirm)
      setStatus({message:'Planning each cliffhanger…',progress:58,error:''})
      const queued = await studio.regenerateAnalysis(seriesId)
      while (true) {
        const job = await studio.getJob(queued.id)
        if (job.state === 'error') throw new Error(job.error || 'Story analysis failed.')
        if (job.state === 'done') break
        setStatus({message:job.message || 'Balancing genre and themes…',progress:82,error:''})
        await wait(1000)
      }
      setStatus({message:'Your Ideaboard is ready.',progress:100,error:''})
      navigate(`/series/${seriesId}`,{replace:true})
    } catch (error) { setStatus((current) => ({...current,error:error.message})); started.current=false }
  }

  useEffect(() => { if (seriesId && confirm && !started.current) { started.current=true; build() } }, [seriesId]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!seriesId || !confirm) return <GenerationLoader error="This build session expired. Your saved series is still available on the dashboard." onBack={() => navigate('/')}/>
  return <GenerationLoader message={status.message} progress={status.progress} error={status.error} onRetry={() => {if (!started.current){started.current=true;build()}}} onBack={() => navigate('/')}/>
}
