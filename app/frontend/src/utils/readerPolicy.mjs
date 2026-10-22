export function safeReaderUrl(value, image = false, origin = 'http://localhost') {
  if (!value || /[\u0000-\u0020\u007f]/.test(value)) return '';
  try {
    const url = new URL(value, origin);
    if (image) return url.origin === origin && /^\/api\/recipes\/[^/]+\/review-assets\//.test(url.pathname)
      ? url.pathname + url.search + url.hash : '';
    if (value.startsWith('#')) return value;
    return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? value : '';
  } catch { return ''; }
}

export function readerHeadings(content) {
  let fenced = false;
  return String(content || '').split(/\r?\n/).flatMap((line, index) => {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; return []; }
    const match = !fenced && line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*$/);
    return match ? [{ line: index + 1, depth: match[1].length, label: match[2].replace(/[*_`]/g, '') }] : [];
  });
}

// CommonMark normally renumbers lists. Preserve each explicit source marker,
// including nonconsecutive knitting row/round numbers.
export function preserveInstructionNumbers() {
  return (tree, file) => {
    const source = String(file.value);
    const visit = (node) => {
      if (node.type === 'list' && node.ordered) {
        node.children.forEach(item => {
          const raw = source.slice(item.position.start.offset, item.position.end.offset);
          const marker = raw.match(/^\s*(\d+)[.)]\s/);
          if (marker) item.data = { ...item.data, hProperties: { ...item.data?.hProperties, value: Number(marker[1]) } };
        });
      }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
}

export function formatSelection(text, start, end, kind) {
  const selected = text.slice(start, end);
  const formats = { heading: ['## ', ''], bold: ['**', '**'], list: ['- ', ''],
    table: ['', '\n\n|  |  |\n| --- | --- |\n|  |  |\n'] };
  const [before, after] = formats[kind];
  return text.slice(0, start) + before + selected + after + text.slice(end);
}
