import { motion } from 'framer-motion'
import { FileText, Sparkles } from 'lucide-react'
import TypingText from './TypingText'

const buildLines = ['Making you the next Shakespeare…','Adding just enough salt to the story…','Teaching your cliffhangers to misbehave…','Giving every character a secret…','Finding the moment nobody skips…']
const episodeLines = ['Writing dialogue that sounds spoken…','Leaving silence where silence wins…','Casting every character distinctly…','Scoring only the moments that need it…','Testing the final cliffhanger…']

export default function GenerationLoader({mode='build',message='',progress=0,error,onRetry,onBack}) {
  const episode = mode === 'episode'
  return <div className="generation-loader">
    <div className="loader-glow" />
    <div className="loader-label"><motion.span animate={{opacity:[1,.25,1]}} transition={{duration:1.1,repeat:Infinity}} />{episode ? 'Generating your episode' : mode === 'refine' ? 'Refining your story' : 'Building your story world'}</div>
    <div className="loader-stage">
      <div className="ingredient ingredient-a"><FileText/></div><div className="ingredient ingredient-b"><Sparkles/></div>
      <motion.div className="loader-orb" animate={{scale:[1,1.08,1],boxShadow:['0 0 20px rgba(230,28,56,.12)','0 0 70px rgba(230,28,56,.5)','0 0 20px rgba(230,28,56,.12)']}} transition={{duration:2.3,repeat:Infinity}}><span/><span/><span/><span/><span/></motion.div>
      <div className="stream stream-left">raw idea · character motive · setting · conflict ·</div><div className="stream stream-right">hook · scene · dialogue · cliffhanger ·</div>
    </div>
    <TypingText lines={episode ? episodeLines : buildLines}/>
    <p className="loader-message">{message || 'Preparing the next story beat…'}</p>
    <div className="loader-track"><motion.div animate={{width:`${Math.max(6,progress)}%`}} /></div>
    {error && <div className="loader-error"><p>{error}</p><div>{onBack && <button className="button ghost" onClick={onBack}>Back</button>}{onRetry && <button className="button primary" onClick={onRetry}>Try again</button>}</div></div>}
  </div>
}
