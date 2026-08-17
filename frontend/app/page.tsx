import Link from 'next/link'
import Nav from '@/components/Nav'
import AnimateOnScroll from '@/components/AnimateOnScroll'

const STEPS = [
  {
    n: '01',
    title: 'Submit',
    body: 'POST an image to /v1/{domain}/analyze. Include an optional clinical question. Receive a job ID immediately. The API never blocks.',
  },
  {
    n: '02',
    title: 'Receive',
    body: 'Get a job ID back as a 202 Accepted. Your request is queued and processing begins within seconds.',
  },
  {
    n: '03',
    title: 'Poll',
    body: 'GET /v1/jobs/{job_id} every 5-10 seconds. When status is "completed", the full structured result is ready.',
  },
]

const DOMAIN_SPOTLIGHTS = [
  {
    name: 'Radiology',
    endpoint: '/v1/radiology/analyze',
    tagline: 'From image to structured report in under 90 seconds',
    description:
      'Radiology departments face mounting pressure: volumes are up, specialist time is scarce, and critical findings cannot wait in a queue. troke returns a structured preliminary assessment on every scan, giving your system what it needs to route and triage before a radiologist reviews. All output is intended for specialist review, not as a standalone finding.',
    stats: [
      { value: '< 90s', label: 'Median result time' },
      { value: '4', label: 'Structured output fields' },
      { value: 'Async', label: 'Never blocks your stack' },
    ],
    benefits: [
      {
        title: 'Triage at scale',
        body: 'Route high-severity findings to the top of the worklist automatically. troke flags severity on every result so your system can prioritize without manual triage.',
      },
      {
        title: 'EHR-ready output',
        body: 'Every field (findings, impression, severity, confidence) maps directly to structured report templates. No parsing of free text.',
      },
    ],
    output: [
      { key: 'findings', value: 'Bilateral lower lobe infiltrates. Blunting of bilateral costophrenic angles.' },
      { key: 'impression', value: 'Findings consistent with community-acquired pneumonia.' },
      { key: 'severity', value: 'moderate', highlight: true },
      { key: 'confidence', value: '0.87' },
    ],
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2C8 2 5 6 5 10c0 2.5 1 4.5 2.5 6L12 22l4.5-6C18 14.5 19 12.5 19 10c0-4-3-8-7-8z" />
        <path d="M9 10c0-1.7 1.3-3 3-3s3 1.3 3 3-1.3 3-3 3-3-1.3-3-3z" />
      </svg>
    ),
  },
  {
    name: 'Dermatology',
    endpoint: '/v1/dermatology/analyze',
    tagline: 'Clinical-grade skin analysis, integrated into any patient flow',
    description:
      'Teledermatology demand has exploded, but specialist access has not kept up. troke pre-screens dermoscopy and clinical photos, returning a structured preliminary assessment, severity indication, and suggested next step to support routing and referral workflows. All results require review by a qualified dermatologist before clinical action.',
    stats: [
      { value: '< 60s', label: 'Median result time' },
      { value: '100+', label: 'Classifiable conditions' },
      { value: '4', label: 'Structured output fields' },
    ],
    benefits: [
      {
        title: 'Teledermatology at scale',
        body: 'Let patients submit images remotely. troke pre-screens and surfaces a structured result so your platform can route to the right specialist automatically.',
      },
      {
        title: 'Actionable by design',
        body: 'The recommendation field returns a direct action: refer, monitor, or treat. No NLP layer between the model output and your decision logic.',
      },
    ],
    output: [
      { key: 'condition', value: 'Melanoma (superficial spreading)' },
      { key: 'severity', value: 'moderate', highlight: true },
      { key: 'recommendation', value: 'Urgent referral to dermatologist recommended.' },
      { key: 'confidence', value: '0.91' },
    ],
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="7" />
        <path d="M21 21l-4.35-4.35" />
        <path d="M8 11h6M11 8v6" />
      </svg>
    ),
  },
  {
    name: 'Pathology',
    endpoint: '/v1/pathology/analyze',
    tagline: 'Pre-screen histology slides before the pathologist reviews',
    description:
      'High-volume pathology labs handle thousands of slides weekly. troke pre-screens histology images to surface preliminary indicators on tissue type and severity, letting pathologists prioritize their review queue. All troke output is preliminary and must be confirmed by a licensed pathologist before any clinical conclusion is drawn.',
    stats: [
      { value: '< 2min', label: 'Median result time' },
      { value: '4', label: 'Structured output fields' },
      { value: 'Async', label: 'Parallel processing' },
    ],
    benefits: [
      {
        title: 'Pathologist leverage',
        body: 'Routine slides get pre-screened. Pathologists spend time on cases that need their judgment, not on documentation of straightforward results.',
      },
      {
        title: 'LIS integration ready',
        body: 'Structured output (diagnosis, tissue type, severity, confidence) slots directly into laboratory information systems without transformation.',
      },
    ],
    output: [
      { key: 'diagnosis', value: 'Invasive ductal carcinoma, grade II' },
      { key: 'tissue_type', value: 'Breast, ductal epithelium' },
      { key: 'severity', value: 'severe', highlight: true },
      { key: 'confidence', value: '0.89' },
    ],
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18" />
        <circle cx="12" cy="12" r="2" />
      </svg>
    ),
  },
  {
    name: 'Ophthalmology',
    endpoint: '/v1/ophthalmology/analyze',
    tagline: 'Population-scale retinal screening through a single API',
    description:
      'Diabetic retinopathy and glaucoma affect millions, but screening capacity is limited by specialist time. troke pre-screens fundus images and OCT scans to flag cases that warrant specialist attention, helping you run population-scale first-pass programs. Flagged cases are intended to be reviewed and confirmed by a qualified ophthalmologist.',
    stats: [
      { value: '< 75s', label: 'Median result time' },
      { value: '4', label: 'Structured output fields' },
      { value: 'Global', label: 'Population-scale ready' },
    ],
    benefits: [
      {
        title: 'Diabetic retinopathy programs',
        body: 'Screen entire diabetic patient populations for DR staging. Route positive findings for specialist review automatically, without building a grading team.',
      },
      {
        title: 'Early detection at scale',
        body: 'Every fundus image gets analyzed, not just those seen in-clinic. Catch glaucoma and AMD before they become critical with systematic, async processing.',
      },
    ],
    output: [
      { key: 'finding', value: 'Non-proliferative diabetic retinopathy' },
      { key: 'affected_structure', value: 'Retinal vasculature, dot hemorrhages present' },
      { key: 'severity', value: 'mild', highlight: true },
      { key: 'confidence', value: '0.93' },
    ],
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
  },
  {
    name: 'Dentistry',
    endpoint: '/v1/dentistry/analyze',
    tagline: 'Automated dental image analysis for modern practice software',
    description:
      'Dental practices and health platforms generate thousands of X-rays and intraoral images weekly. troke pre-screens dental images to surface preliminary findings and severity indicators, helping software teams build smarter triage and referral workflows. All output is preliminary and must be reviewed by a qualified dentist before any clinical decision is made.',
    stats: [
      { value: '< 60s', label: 'Median result time' },
      { value: '4', label: 'Structured output fields' },
      { value: 'Async', label: 'Never blocks your stack' },
    ],
    benefits: [
      {
        title: 'Automated triage for dental platforms',
        body: 'Route urgent findings such as abscesses or advanced bone loss to the top of the worklist. troke surfaces severity on every image so your system can prioritize without manual review.',
      },
      {
        title: 'Practice management integration',
        body: 'Structured output (finding, affected area, severity, confidence) slots directly into dental practice management systems and patient record templates.',
      },
    ],
    output: [
      { key: 'finding', value: 'Periapical abscess with bone resorption' },
      { key: 'affected_area', value: 'Lower left first molar, periapical region' },
      { key: 'severity', value: 'moderate', highlight: true },
      { key: 'confidence', value: '0.88' },
    ],
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2C9 2 7 4 7 6c0 1.5.5 2.5 1 3.5C9 11 9 13 8 15c-.5 1.5-.5 3 .5 4s2.5 1 3.5 0 2-1 3.5 0 2.5.5 3.5-.5.5-2.5 0-3.5C18 13 18 11 19 9.5c.5-1 1-2 1-3.5 0-2-2-4-5-4h-3z" />
      </svg>
    ),
  },
]

const USE_CASES = [
  {
    title: 'Clinical Decision Support',
    body: 'Surface structured findings alongside patient records. Let clinicians triage faster with AI-assisted interpretation, without replacing their judgement.',
  },
  {
    title: 'Health Record Integration',
    body: 'Embed troke into EHR workflows to auto-populate structured fields from imaging studies. Reduce manual transcription and documentation overhead.',
  },
  {
    title: 'Medical Device Software',
    body: 'Add medical AI to regulated software without hosting a model. troke handles inference; you stay focused on your product.',
  },
]

const SEVERITY_COLORS: Record<string, string> = {
  mild: 'text-yellow-400',
  moderate: 'text-orange-400',
  severe: 'text-red-400',
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0f] overflow-x-hidden">
      <Nav />

      {/* Hero */}
      <section className="relative text-center px-6 pt-24 pb-20 max-w-2xl mx-auto">
        <div className="hero-glow" />

        <div className="relative z-10">
          <div
            className="inline-block bg-[#1a6fff18] text-[#4d9fff] text-xs font-semibold px-3 py-1 rounded-full border border-[#1a6fff44] tracking-widest mb-6 animate-fade-up"
            style={{ animationDelay: '0ms' }}
          >
            MEDICAL AI INFERENCE API
          </div>

          <h1
            className="text-5xl font-extrabold tracking-tight leading-tight mb-5 text-white animate-fade-up"
            style={{ animationDelay: '80ms' }}
          >
            Radiology. Dermatology.<br />Pathology. Ophthalmology. Dentistry.
          </h1>

          <p
            className="text-[#6b8ab0] text-lg leading-relaxed mb-8 animate-fade-up"
            style={{ animationDelay: '160ms' }}
          >
            Structured medical image pre-screening via a single REST API.<br />
            Built for clinical software teams.
          </p>

          <p
            className="text-[#4a5568] text-xs leading-relaxed mb-6 animate-fade-up max-w-lg mx-auto"
            style={{ animationDelay: '200ms' }}
          >
            For clinical decision support only. troke assists workflows with preliminary image analysis intended for review by a qualified clinician. Not a diagnostic tool.
          </p>

          <div
            className="flex gap-3 justify-center items-center animate-fade-up"
            style={{ animationDelay: '240ms' }}
          >
            <div className="btn-orbit">
              <Link href="/request-access" className="btn-orbit-inner px-7 py-3">
                Request Access
              </Link>
            </div>
            <Link
              href="/docs"
              className="text-[#6b8ab0] border border-[#1a3a6e] px-6 py-3 rounded-md hover:text-white hover:border-[#4d9fff] transition-all duration-200"
            >
              View Docs
            </Link>
          </div>

          {/* Floating code block */}
          <div
            className="mt-12 bg-[#0d1520] border border-[#1a3a6e] rounded-xl px-6 py-5 text-left font-mono text-sm text-[#4d9fff] leading-7 animate-float animate-fade-up shadow-[0_0_40px_#1a6fff0d]"
            style={{ animationDelay: '320ms' }}
          >
            <div className="flex items-center gap-2 mb-3 pb-3 border-b border-[#1a2a4a]">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
              <span className="text-[#4a5568] text-xs ml-1">troke API</span>
            </div>
            <span className="text-[#6b8ab0]">POST</span> /v1/radiology/analyze<br />
            <span className="text-[#6b8ab0]">{'>'}</span>{' '}
            <span className="text-green-400">{'{ "job_id": "3f2a1b4c-..." }'}</span><br />
            <span className="text-[#6b8ab0]">GET</span> /v1/jobs/3f2a1b4c-...<br />
            <span className="text-[#6b8ab0]">{'>'}</span>{' '}
            <span className="text-green-400">{'{ "status": "completed", "structured": { ... } }'}</span>
          </div>
        </div>
      </section>

      {/* Domain spotlights */}
      <section className="max-w-5xl mx-auto px-6 py-20 border-t border-[#1a2a4a]">
        <AnimateOnScroll className="text-center mb-20">
          <h2 className="text-2xl font-bold text-white mb-2">Built for every specialty</h2>
          <p className="text-[#6b8ab0] text-sm">Specialized models. Consistent API. Real clinical value.</p>
        </AnimateOnScroll>

        <div className="space-y-32">
          {DOMAIN_SPOTLIGHTS.map((d, i) => (
            <AnimateOnScroll key={d.name}>
              <div className={`flex flex-col ${i % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'} gap-12 md:gap-16 items-center`}>

                {/* Text */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="text-[#4d9fff]">{d.icon}</div>
                    <span className="text-[#4d9fff] text-xs font-semibold uppercase tracking-widest">{d.name}</span>
                  </div>

                  <h3 className="text-2xl font-bold text-white mb-4 leading-snug">{d.tagline}</h3>
                  <p className="text-[#6b8ab0] text-sm leading-relaxed mb-8">{d.description}</p>

                  {/* Stats */}
                  <div className="flex gap-8 mb-8 pb-8 border-b border-[#1a2a4a]">
                    {d.stats.map((s) => (
                      <div key={s.label}>
                        <div className="text-xl font-extrabold text-white">{s.value}</div>
                        <div className="text-[#4a5568] text-xs mt-0.5">{s.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Benefits */}
                  <div className="space-y-5">
                    {d.benefits.map((b) => (
                      <div key={b.title} className="flex gap-3">
                        <div className="mt-1.5 w-1 h-1 rounded-full bg-[#1a6fff] flex-shrink-0" />
                        <div>
                          <div className="text-white text-sm font-semibold mb-1">{b.title}</div>
                          <div className="text-[#6b8ab0] text-sm leading-relaxed">{b.body}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Output preview */}
                <div className="flex-1 w-full min-w-0">
                  <div className="bg-[#0d1520] border border-[#1a3a6e] rounded-xl overflow-hidden shadow-[0_0_60px_#1a6fff08]">
                    <div className="flex items-center gap-2 px-5 py-3 border-b border-[#1a2a4a] bg-[#0a1018]">
                      <div className="w-2 h-2 rounded-full bg-red-500/50" />
                      <div className="w-2 h-2 rounded-full bg-yellow-500/50" />
                      <div className="w-2 h-2 rounded-full bg-green-500/50" />
                      <span className="text-[#4a5568] text-xs font-mono ml-2">{d.endpoint}</span>
                    </div>

                    <div className="flex items-center gap-3 px-5 py-2.5 border-b border-[#1a2a4a] bg-[#0c1520]">
                      <span className="text-green-400 text-xs font-mono font-semibold">200 OK</span>
                      <span className="text-[#4a5568] text-xs">·</span>
                      <span className="text-[#4a5568] text-xs font-mono">status: <span className="text-[#4d9fff]">completed</span></span>
                    </div>

                    <div className="px-5 py-4 font-mono text-xs space-y-3">
                      <div className="text-[#4a5568] text-xs mb-1">structured:</div>
                      {d.output.map((f) => (
                        <div key={f.key} className="flex gap-0 pl-3">
                          <span className="text-[#4d9fff] flex-shrink-0">{f.key}:{' '}</span>
                          <span className={`leading-relaxed ml-1 ${f.highlight ? (SEVERITY_COLORS[f.value] ?? 'text-[#e2e8f0]') : 'text-[#a0b4cc]'}`}>
                            {f.value}
                          </span>
                        </div>
                      ))}
                    </div>

                    <div className="px-5 py-3 border-t border-[#1a2a4a] bg-[#0a1018]">
                      <span className="text-[#2a4a6e] text-xs font-mono">raw_output also available</span>
                    </div>
                  </div>
                </div>

              </div>
            </AnimateOnScroll>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-6 py-20 border-t border-[#1a2a4a]">
        <AnimateOnScroll className="text-center mb-12">
          <h2 className="text-2xl font-bold text-white mb-2">How it works</h2>
          <p className="text-[#6b8ab0] text-sm">Three steps. No polling complexity on your end.</p>
        </AnimateOnScroll>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {STEPS.map((s, i) => (
            <AnimateOnScroll key={s.n} delay={i * 80}>
              <div className="card-hover bg-[#0d1520] border border-[#1a3a6e] rounded-xl p-6 h-full">
                <div className="text-[#1a6fff] font-mono text-xs font-bold mb-4">{s.n}</div>
                <h3 className="text-white font-semibold text-base mb-2">{s.title}</h3>
                <p className="text-[#6b8ab0] text-sm leading-relaxed">{s.body}</p>
              </div>
            </AnimateOnScroll>
          ))}
        </div>

        <AnimateOnScroll delay={240} className="text-center mt-8">
          <p className="text-[#6b8ab0] text-sm">
            Typical latency: <span className="text-white font-medium">30-90 seconds</span>. All jobs are async. No timeouts, no blocking.
          </p>
        </AnimateOnScroll>
      </section>

      {/* Use cases */}
      <section className="max-w-4xl mx-auto px-6 py-20 border-t border-[#1a2a4a]">
        <AnimateOnScroll className="text-center mb-12">
          <h2 className="text-2xl font-bold text-white">Built for enterprise clinical software</h2>
        </AnimateOnScroll>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {USE_CASES.map((u, i) => (
            <AnimateOnScroll key={u.title} delay={i * 80}>
              <div className="border-l-2 border-[#1a6fff33] pl-4 hover:border-[#1a6fff] transition-colors duration-300">
                <h3 className="text-white font-semibold text-sm mb-2">{u.title}</h3>
                <p className="text-[#6b8ab0] text-sm leading-relaxed">{u.body}</p>
              </div>
            </AnimateOnScroll>
          ))}
        </div>
      </section>

      {/* Clinical disclaimer */}
      <section className="max-w-4xl mx-auto px-6 py-16 border-t border-[#1a2a4a]">
        <AnimateOnScroll>
          <div className="bg-[#0d1520] border border-[#1a3a6e] rounded-xl px-8 py-6 flex gap-5 items-start">
            <div className="flex-shrink-0 mt-0.5">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4d9fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <div>
              <p className="text-white text-sm font-semibold mb-2">Clinical decision support, not a diagnostic system</p>
              <p className="text-[#6b8ab0] text-sm leading-relaxed">
                troke provides preliminary image pre-screening to support clinical workflows and software. It is not a medical device, does not produce clinical diagnoses, and is not a substitute for professional medical judgement. All output must be reviewed and validated by a qualified healthcare professional before any clinical decision is made. AI systems can and do make errors, and no output from troke should be acted upon without clinician oversight.
              </p>
            </div>
          </div>
        </AnimateOnScroll>
      </section>

      {/* CTA */}
      <section className="relative text-center px-6 py-24 border-t border-[#1a2a4a] overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,#1a6fff0d_0%,transparent_65%)] pointer-events-none" />
        <AnimateOnScroll className="relative z-10">
          <h2 className="text-3xl font-extrabold text-white mb-3 tracking-tight">Ready to integrate?</h2>
          <p className="text-[#6b8ab0] text-sm mb-8">Enterprise access only. We review every application.</p>
          <div className="btn-orbit">
            <Link href="/request-access" className="btn-orbit-inner px-10 py-3.5">
              Request Access
            </Link>
          </div>
        </AnimateOnScroll>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#1a2a4a] px-6 py-8 flex justify-between items-center max-w-4xl mx-auto">
        <span className="text-white font-extrabold tracking-tight">troke</span>
        <div className="flex gap-6">
          <Link href="/docs" className="text-[#6b8ab0] text-sm hover:text-white transition-colors">Docs</Link>
          <Link href="/request-access" className="text-[#6b8ab0] text-sm hover:text-white transition-colors">Request Access</Link>
        </div>
        <span className="text-[#4a5568] text-xs">© {new Date().getFullYear()} Troke</span>
      </footer>
    </div>
  )
}
