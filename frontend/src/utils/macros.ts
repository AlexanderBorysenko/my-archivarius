type ManifestEntry = { kind: string; status: string; has_poster: boolean }
type Manifest = Record<string, ManifestEntry>

function escapeHtml(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function decodePayload(raw: string): any {
  const t = raw.trim()
  try { return JSON.parse(t) } catch {}
  try { return JSON.parse(decodeURIComponent(escape(atob(t)))) } catch { return null }
}

function isReadyPhoto(m: Manifest, code: string): boolean {
  return m[code]?.status === 'ready' && m[code]?.kind === 'photo'
}

function renderGallery(p: any, m: Manifest): string {
  const codes: string[] = (p?.images || []).filter((c: string) => isReadyPhoto(m, c))
  if (!codes.length) return ''
  const items = codes
    .map(
      (c) =>
        `<a class="diary-gallery__item" href="/api/media/${c}" target="_blank" rel="noopener">` +
        `<img src="/api/media/${c}" loading="lazy"></a>`
    )
    .join('')
  const cap = p?.caption
    ? `<figcaption class="diary-gallery__caption">${escapeHtml(p.caption)}</figcaption>`
    : ''
  return `<figure class="diary-gallery"><div class="diary-gallery__grid">${items}</div>${cap}</figure>`
}

function renderFigure(p: any, m: Manifest): string {
  const c = p?.image
  if (!isReadyPhoto(m, c)) return ''
  const align = ['left', 'right', 'center', 'full'].includes(p?.align) ? p.align : 'left'
  const width = [25, 33, 50, 100].includes(p?.width) ? p.width : 33
  const wStyle = align === 'full' ? '' : ` style="width:${width}%"`
  const cap = p?.caption
    ? `<figcaption class="diary-figure__caption">${escapeHtml(p.caption)}</figcaption>`
    : ''
  return (
    `<figure class="diary-figure diary-figure--${align}"${wStyle}>` +
    `<img src="/api/media/${c}" loading="lazy">${cap}</figure>`
  )
}

const MACRO_RENDERERS: Record<string, (p: any, m: Manifest) => string> = {
  gallery: renderGallery,
  figure: renderFigure,
}

export function injectMacros(html: string, manifest: Manifest): string {
  // unwrap a <p> whose only content is a macro comment, then expand all macros
  const unwrapped = html.replace(
    /<p>\s*(<!--\s*macro:[a-z0-9_]+\s+.+?\s*-->)\s*<\/p>/gs,
    '$1'
  )
  return unwrapped.replace(
    /<!--\s*macro:([a-z0-9_]+)\s+(.+?)\s*-->/gs,
    (_full, name, raw) => {
      const fn = MACRO_RENDERERS[name]
      if (!fn) return ''
      const payload = decodePayload(raw)
      return payload ? fn(payload, manifest || {}) : ''
    }
  )
}
