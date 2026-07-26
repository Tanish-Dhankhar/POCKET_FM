import { motion } from 'framer-motion'

export default function ThemeBars({themes=[]}) {
  return <div className="theme-bars">{themes.slice(0,4).map((theme,index) => <div className="theme-bar" key={`${theme.label}-${index}`}><strong>{theme.label}</strong><div><motion.span initial={{width:0}} animate={{width:`${theme.percentage || 0}%`}} transition={{duration:.55,delay:index*.06}} /></div><em>{theme.percentage || 0}%</em></div>)}</div>
}
