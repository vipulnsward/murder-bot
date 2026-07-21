import { useEffect, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export function Knowledge() {
  const [selected, setSelected] = useState<string | null>(null)
  const [guideSearch, setGuideSearch] = useState('')
  const docs = useQuery({ queryKey: ['knowledge-docs'], queryFn: api.getKnowledgeDocs })
  const document = useQuery({
    queryKey: ['knowledge-doc', selected],
    queryFn: () => api.getKnowledgeDoc(selected!),
    enabled: selected !== null,
  })
  const guides = useQuery({
    queryKey: ['guides', guideSearch],
    queryFn: () => api.getGuides({ q: guideSearch.trim() }),
  })

  useEffect(() => {
    if (!selected && docs.data?.docs.length) setSelected(docs.data.docs[0])
  }, [docs.data, selected])

  return (
    <div>
      <div className="page-heading">
        <div><p className="eyebrow">Game reference</p><h1>Knowledge</h1></div>
        <span className="text-sm text-muted tabular-nums">{docs.data?.docs.length ?? 0} documents</span>
      </div>

      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="card min-w-0">
          <p className="eyebrow">Knowledge base</p><h2 className="mb-4 mt-1 text-lg font-semibold">Documents</h2>
          {docs.isPending && <p className="text-sm text-muted">Loading documents…</p>}
          {docs.isError && <div className="offline-banner mb-0">Documents are unavailable. Check the backend connection.</div>}
          {docs.data && (docs.data.docs.length ? (
            <nav aria-label="Knowledge documents" className="space-y-1">
              {docs.data.docs.map((name) => (
                <button className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm transition ${selected === name ? 'bg-surface-2 text-accent' : 'text-muted hover:bg-surface-2 hover:text-text'}`} key={name} onClick={() => setSelected(name)} title={name} type="button">
                  {name.replace(/\.md$/i, '')}
                </button>
              ))}
            </nav>
          ) : <div className="empty-state p-5 text-sm">No knowledge documents found.</div>)}
        </aside>

        <section className="card min-w-0">
          <p className="eyebrow">{document.data?.name ?? 'Document'}</p>
          {!selected && !docs.isPending && <div className="empty-state mt-4">Select a document to read it.</div>}
          {selected && document.isPending && <p className="mt-4 text-sm text-muted">Loading document…</p>}
          {selected && document.isError && <div className="error-banner mt-4">Could not load this document.</div>}
          {document.data && (document.data.markdown.trim() ? <Markdown markdown={document.data.markdown} /> : <div className="empty-state mt-4">This document is empty.</div>)}
        </section>
      </div>

      <section className="card mt-4">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div><p className="eyebrow">External references</p><h2 className="mt-1 text-lg font-semibold">Guides</h2></div>
          <label className="field-label w-full sm:w-80">Search guides
            <input className="field" onChange={(event) => setGuideSearch(event.target.value)} placeholder="Title, category, or topic" type="search" value={guideSearch} />
          </label>
        </div>
        {guides.isPending && <p className="text-sm text-muted">Loading guides…</p>}
        {guides.isError && <div className="offline-banner mb-0">Guides are unavailable. Check the backend connection.</div>}
        {guides.data && (guides.data.guides.length ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{guides.data.guides.map((guide) => (
            <a className="rounded-lg border border-border bg-surface-2 p-4 transition hover:border-accent" href={guide.url} key={guide.url} rel="noreferrer" target="_blank">
              <span className="text-xs uppercase tracking-[0.06em] text-muted">{guide.category ?? 'Guide'}</span>
              <h3 className="mt-1 font-medium text-accent">{guide.title}</h3>
              <p className="mt-2 text-sm text-muted">{guide.summary ?? 'No summary available.'}</p>
            </a>
          ))}</div>
        ) : <div className="empty-state">No guides match this search.</div>)}
      </section>
    </div>
  )
}

function Markdown({ markdown }: { markdown: string }) {
  const lines = markdown.split('\n')
  return <article className="mt-4 space-y-2 text-sm leading-7">{lines.map(renderLine)}</article>
}

function renderLine(line: string, index: number): ReactNode {
  const heading = /^(#{1,6})\s+(.*)$/.exec(line)
  if (heading) {
    const level = heading[1].length
    const className = level === 1 ? 'pt-2 text-xl font-semibold' : level === 2 ? 'pt-4 text-lg font-semibold' : 'pt-3 font-semibold'
    return <h2 className={className} key={index}>{heading[2]}</h2>
  }
  if (/^[-*]\s+/.test(line)) return <p className="pl-4 text-muted before:mr-2 before:content-['•']" key={index}>{line.replace(/^[-*]\s+/, '')}</p>
  if (!line.trim()) return <div className="h-2" key={index} />
  return <p className="whitespace-pre-wrap break-words text-muted" key={index}>{line}</p>
}
