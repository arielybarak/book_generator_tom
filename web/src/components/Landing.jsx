import { motion } from 'framer-motion'
import { Button } from './ui/Button'
import { TactilePageMock } from './TactilePageMock'
import { useLang } from '../lib/i18n'

const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08, duration: 0.5 } }),
}

const GALLERY = [
  { word: 'חָתוּל', label: 'חתול' },
  { word: 'כֶּלֶב', label: 'כלב' },
  { word: 'פְּרָחִים', label: 'פרחים' },
]

export function Landing({ onStart }) {
  const { t } = useLang()
  return (
    <>
      {/* Hero */}
      <section className="mx-auto grid max-w-5xl items-center gap-10 px-6 py-10 md:grid-cols-2 md:gap-12 md:py-16">
        {/* Copy + CTA */}
        <motion.div initial="hidden" animate="show" className="text-center md:text-start">
          <motion.p
            custom={0}
            variants={fade}
            className="bg-accent-soft text-accent-text mb-3 inline-block rounded-full px-4 py-1 text-sm font-semibold"
          >
            {t.tagline}
          </motion.p>
          <motion.h1
            custom={1}
            variants={fade}
            className="text-ink text-4xl leading-tight font-bold md:text-5xl"
          >
            {t.landing.headline}
          </motion.h1>
          <motion.p custom={2} variants={fade} className="text-muted mt-5 text-lg">
            {t.landing.sub}
          </motion.p>
          <motion.div custom={3} variants={fade} className="mt-8">
            <Button size="lg" onClick={onStart} className="text-xl">
              {t.landing.cta}
              <span aria-hidden="true">{t.common.arrowNext}</span>
            </Button>
            <p className="text-muted mt-4 text-sm">{t.landing.note}</p>
          </motion.div>
        </motion.div>

        {/* Hero visual */}
        <motion.div
          initial={{ opacity: 0, scale: 0.94, rotate: -2 }}
          animate={{ opacity: 1, scale: 1, rotate: -2 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mx-auto w-full max-w-sm"
        >
          <TactilePageMock />
        </motion.div>
      </section>

      {/* Example gallery */}
      <section
        aria-label={t.landing.galleryTitle}
        className="border-line bg-surface/50 border-t px-6 py-12"
      >
        <div className="mx-auto max-w-5xl">
          <motion.h2
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="text-ink mb-8 text-center text-2xl font-bold"
          >
            {t.landing.galleryTitle}
          </motion.h2>
          <div className="grid gap-6 sm:grid-cols-3">
            {GALLERY.map(({ word, label }, i) => (
              <motion.div
                key={word}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.5 }}
              >
                <TactilePageMock word={word} />
                <p className="text-muted mt-3 text-center text-sm font-medium">{label}</p>
              </motion.div>
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="mt-10 text-center"
          >
            <Button size="lg" onClick={onStart}>
              {t.landing.cta}
              <span aria-hidden="true">{t.common.arrowNext}</span>
            </Button>
          </motion.div>
        </div>
      </section>
    </>
  )
}
