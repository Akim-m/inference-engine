import fs from 'fs'
import path from 'path'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import Nav from '@/components/Nav'
import DocsSidebar from '@/components/DocsSidebar'

function toSlug(text: string) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function extractHeadings(md: string) {
  return [...md.matchAll(/^(#{1,3})\s+(.+)$/gm)].map(([, hashes, text]) => ({
    text,
    slug: toSlug(text),
    level: hashes.length,
  }))
}

function nodeText(children: React.ReactNode): string {
  if (typeof children === 'string') return children
  if (Array.isArray(children)) return children.map(nodeText).join('')
  return ''
}

export default function DocsPage() {
  let content = ''
  try {
    content = fs.readFileSync(path.join(process.cwd(), '..', 'docs', 'api.md'), 'utf-8')
  } catch {
    content = '# Documentation\n\nDocs not available.'
  }

  const headings = extractHeadings(content)

  const components: Components = {
    h1: ({ children }) => <h1 id={toSlug(nodeText(children))}>{children}</h1>,
    h2: ({ children }) => <h2 id={toSlug(nodeText(children))}>{children}</h2>,
    h3: ({ children }) => <h3 id={toSlug(nodeText(children))}>{children}</h3>,
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      <Nav />
      <div className="max-w-5xl mx-auto px-6 py-12 flex gap-12">
        <DocsSidebar headings={headings} />
        <article className="flex-1 min-w-0 prose prose-invert prose-sm max-w-none
          prose-headings:font-bold prose-headings:text-white
          prose-p:text-[#6b8ab0] prose-p:leading-relaxed
          prose-a:text-[#4d9fff] prose-a:no-underline hover:prose-a:underline
          prose-code:text-[#4d9fff] prose-code:bg-[#0d1520] prose-code:px-1 prose-code:rounded
          prose-pre:bg-[#0d1520] prose-pre:border prose-pre:border-[#1a3a6e]
          prose-table:text-sm prose-th:text-[#6b8ab0] prose-td:text-[#6b8ab0]
          prose-strong:text-white prose-hr:border-[#1a2a4a]
          prose-li:text-[#6b8ab0]">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {content}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  )
}
